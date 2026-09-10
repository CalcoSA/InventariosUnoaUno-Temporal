const URL_BASE_MAESTRA =
  'https://docs.google.com/spreadsheets/d/1q34wHfO08PDclMA2zSNf03naVkSllG6lCRcHu6dGdg4/edit?gid=1323363823#gid=1323363823';

const URL_RESUMEN_GENERAL =
  'https://docs.google.com/spreadsheets/d/1_Kj9mXyd5q8y1wx6D0sSmbapiGugvxj3yBo437xQk8M/edit?gid=0#gid=0';


function doGet() {
  return HtmlService
    .createHtmlOutputFromFile('Index')
    .setTitle('Inventarios PDV')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}


function obtenerLibroMaestro_() {
  return SpreadsheetApp.openByUrl(URL_BASE_MAESTRA);
}


function obtenerPuntosVenta() {
  const libro = obtenerLibroMaestro_();
  const control = libro.getSheetByName('Control Formularios');

  if (!control || control.getLastRow() < 2) {
    return [];
  }

  return control
    .getRange(2, 1, control.getLastRow() - 1, 4)
    .getDisplayValues()
    .filter(fila =>
      fila[1] !== '' &&
      fila[2].trim().toUpperCase() === 'LISTO' &&
      fila[3] !== ''
    )
    .map(fila => fila[1].trim())
    .filter((nombre, posicion, lista) =>
      lista.indexOf(nombre) === posicion
    )
    .sort((a, b) => a.localeCompare(b, 'es'));
}


function obtenerCategorias(puntoVenta) {
  return [...new Set(
    obtenerProductos(puntoVenta)
      .map(producto => producto.categoria)
      .filter(categoria => categoria !== '')
  )].sort((a, b) => a.localeCompare(b, 'es'));
}


function obtenerProductos(puntoVenta, categoriaSeleccionada) {
  const libroPDV = obtenerLibroPDV_(puntoVenta);
  const hoja = buscarHoja_(libroPDV, 'Uno a Uno');

  if (!hoja) {
    throw new Error(
      'No se encontró la hoja "Uno a Uno" para ' + puntoVenta + '.'
    );
  }

  const ultimaFila = hoja.getLastRow();
  const ultimaColumna = hoja.getLastColumn();

  if (ultimaFila < 2) {
    return [];
  }

  const datos = hoja
    .getRange(1, 1, ultimaFila, ultimaColumna)
    .getDisplayValues();
  const valores = hoja
    .getRange(1, 1, ultimaFila, ultimaColumna)
    .getValues();

  const encabezados = datos[0].map(normalizar_);

  let columnaCategoria = buscarIndice_(
    encabezados,
    ['categoria']
  );

  let columnaItem = buscarIndice_(
    encabezados,
    ['item', 'codigo', 'cod', 'id producto']
  );

  let columnaProducto = buscarIndice_(
    encabezados,
    ['nombre producto', 'producto', 'descripcion', 'desc item']
  );

  let columnaUDM = buscarIndice_(
    encabezados,
    [
      'desc u m',
      'desc um',
      'descripcion unidad de medida',
      'udm',
      'unidad de medida',
      'unidad',
      'um empaque'
    ]
  );

  let columnaFactor = buscarIndice_(
    encabezados,
    ['factor', 'factor um', 'factor u m', 'factor udm']
  );

  if (columnaCategoria === -1) columnaCategoria = 0;
  if (columnaItem === -1) columnaItem = 1;
  if (columnaProducto === -1) columnaProducto = 2;
  if (columnaUDM === -1) columnaUDM = 3;

  const categoriaBuscada = normalizar_(categoriaSeleccionada);

  return datos
    .slice(1)
    .filter(fila =>
      String(fila[columnaItem]).trim() !== '' &&
      String(fila[columnaProducto]).trim() !== ''
    )
    .map((fila, posicion) => ({
      id: posicion + 1,
      categoria:
        String(fila[columnaCategoria]).trim() || 'Uno a Uno',
      item: String(fila[columnaItem]).trim(),
      producto: String(fila[columnaProducto]).trim(),
      udm: String(fila[columnaUDM]).trim(),
      factor: columnaFactor === -1
        ? obtenerFactorCorrecto_(fila[columnaUDM], 1)
        : obtenerFactorCorrecto_(
            fila[columnaUDM],
            valores[posicion + 1][columnaFactor]
          )
    }))
    .filter(producto =>
      !categoriaBuscada ||
      normalizar_(producto.categoria) === categoriaBuscada
    );
}


function guardarInventario(datos) {
  if (
    !datos ||
    !datos.puntoVenta ||
    !datos.fecha ||
    !datos.categoria
  ) {
    throw new Error(
      'Debe seleccionar el PDV, la fecha y la categoría.'
    );
  }

  if (!Array.isArray(datos.conteos) || datos.conteos.length === 0) {
    throw new Error('No se recibieron conteos para guardar.');
  }

  const tieneValor = valor =>
    valor !== '' && valor !== null && valor !== undefined;

  const conteosValidos = datos.conteos.filter(conteo =>
    tieneValor(conteo.cerrado) || tieneValor(conteo.abierto)
  );

  if (conteosValidos.length === 0) {
    throw new Error(
      'Debe registrar al menos una cantidad en Cerrado o Abierto.'
    );
  }

  const idRegistro = Utilities.getUuid();
  const fechaHora = new Date();
  const libroPDV = obtenerLibroPDV_(datos.puntoVenta);
  const factoresPorItem = obtenerFactoresPorItem_(libroPDV);

  const filas = conteosValidos.map(conteo => {
    const cerrado = convertirNumero_(conteo.cerrado, 0);
    const abierto = convertirNumero_(conteo.abierto, 0);
    const item = String(conteo.item || '').trim();
    const factorBase = factoresPorItem.get(item);
    const factor = factorBase > 0 ? factorBase : 1;

    if (isNaN(cerrado) || cerrado < 0) {
      throw new Error(
        'La cantidad cerrada del ítem ' + conteo.item +
        ' no es válida.'
      );
    }

    if (isNaN(abierto) || abierto < 0) {
      throw new Error(
        'La cantidad abierta del ítem ' + conteo.item +
        ' no es válida.'
      );
    }

    if (isNaN(factor) || factor <= 0) {
      throw new Error(
        'El factor del ítem ' + conteo.item + ' no es válido.'
      );
    }

    const conteoFisico = (cerrado * factor) + abierto;

    return [
      idRegistro,
      fechaHora,
      datos.fecha,
      datos.puntoVenta,
      datos.categoria,
      conteo.item,
      conteo.producto,
      conteo.udm,
      cerrado,
      abierto,
      factor,
      conteoFisico
    ];
  });

  const bloqueo = LockService.getScriptLock();
  bloqueo.waitLock(30000);

  try {
    const nombreHoja = 'Conteos Inventarios';
    let hojaDestino = libroPDV.getSheetByName(nombreHoja);

    if (!hojaDestino) {
      hojaDestino = libroPDV.insertSheet(nombreHoja);
    }

    const encabezados = [
      'ID Registro',
      'Fecha y hora',
      'Fecha inventario',
      'Punto de venta',
      'Categoría',
      'Item',
      'Nombre Producto',
      'Desc. U.M.',
      'Cerrado',
      'Abierto',
      'Factor',
      'Conteo Físico'
    ];

    if (hojaDestino.getLastRow() === 0) {
      hojaDestino.appendRow(encabezados);
    } else {
      hojaDestino
        .getRange(1, 1, 1, encabezados.length)
        .setValues([encabezados]);
    }

    hojaDestino
      .getRange(1, 1, 1, encabezados.length)
      .setBackground('#4A2B14')
      .setFontColor('#FFFFFF')
      .setFontWeight('bold');

    if (hojaDestino.getLastRow() >= 2) {
      const registrosExistentes = hojaDestino
        .getRange(2, 3, hojaDestino.getLastRow() - 1, 3)
        .getValues();

      const yaRegistrado = registrosExistentes.some(fila =>
        claveFecha_(fila[0]) === claveFecha_(datos.fecha) &&
        normalizar_(fila[1]) === normalizar_(datos.puntoVenta) &&
        normalizar_(fila[2]) === normalizar_(datos.categoria)
      );

      if (yaRegistrado) {
        throw new Error(
          'La categoría "' + datos.categoria + '" ya fue guardada para ' +
          datos.puntoVenta + ' en esta fecha.'
        );
      }
    }

    hojaDestino
      .getRange(
        hojaDestino.getLastRow() + 1,
        1,
        filas.length,
        filas[0].length
      )
      .setValues(filas);

    hojaDestino.autoResizeColumns(1, encabezados.length);

    actualizarResumenInventario_(libroPDV);
    registrarEnResumenGeneral_(filas);
  } finally {
    bloqueo.releaseLock();
  }

  return {
    correcto: true,
    mensaje: 'Inventario guardado correctamente.',
    registros: filas.length
  };
}


function actualizarResumenInventario_(libroPDV) {
  const nombreHoja = 'Resumen Inventario';
  const hojaConteos = libroPDV.getSheetByName('Conteos Inventarios');
  let hojaResumen = libroPDV.getSheetByName(nombreHoja);

  if (!hojaResumen) {
    hojaResumen = libroPDV.insertSheet(nombreHoja);
  }

  const encabezados = [
    'Fecha inventario',
    'Punto de venta',
    'Item',
    'Descripcionproducto',
    'UDM',
    'Cerrado',
    'Abierto',
    'Factor',
    'ConteoFisico',
    'Última actualización'
  ];

  if (!hojaConteos || hojaConteos.getLastRow() < 2) {
    hojaResumen.clearContents();
    hojaResumen.getRange(1, 1, 1, encabezados.length)
      .setValues([encabezados]);
    aplicarFormatoResumen_(hojaResumen, encabezados.length);
    return;
  }

  const datos = hojaConteos
    .getRange(
      1,
      1,
      hojaConteos.getLastRow(),
      hojaConteos.getLastColumn()
    )
    .getValues();

  const encabezadosConteos = datos[0].map(normalizar_);
  const columnaFecha = buscarIndice_(
    encabezadosConteos,
    ['fecha inventario']
  );
  const columnaPDV = buscarIndice_(
    encabezadosConteos,
    ['punto de venta', 'pdv']
  );
  const columnaItem = buscarIndice_(
    encabezadosConteos,
    ['item', 'codigo', 'cod']
  );
  const columnaProducto = buscarIndice_(
    encabezadosConteos,
    ['nombre producto', 'producto']
  );
  const columnaUDM = buscarIndice_(
    encabezadosConteos,
    ['desc u m', 'desc um', 'udm', 'unidad de medida']
  );
  const columnaCerrado = buscarIndice_(
    encabezadosConteos,
    ['cerrado']
  );
  const columnaAbierto = buscarIndice_(
    encabezadosConteos,
    ['abierto']
  );
  const columnaFactor = buscarIndice_(
    encabezadosConteos,
    ['factor', 'factor um', 'factor u m', 'factor udm']
  );

  const factoresPorItem = obtenerFactoresPorItem_(libroPDV);

  const columnasObligatorias = [
    columnaFecha,
    columnaPDV,
    columnaItem,
    columnaProducto,
    columnaUDM,
    columnaCerrado,
    columnaAbierto
  ];

  if (columnasObligatorias.some(indice => indice === -1)) {
    throw new Error(
      'No se pudieron identificar todas las columnas de Conteos Inventarios.'
    );
  }

  const agrupados = new Map();

  datos.slice(1).forEach(fila => {
    const fecha = fila[columnaFecha];
    const puntoVenta = fila[columnaPDV];
    const item = String(fila[columnaItem] || '').trim();
    const producto = fila[columnaProducto];
    const udm = fila[columnaUDM];
    const cerrado = Number(fila[columnaCerrado]) || 0;
    const abierto = Number(fila[columnaAbierto]) || 0;
    const factorGuardado = columnaFactor === -1
      ? NaN
      : obtenerFactorCorrecto_(udm, fila[columnaFactor]);
    const factorBase = factoresPorItem.get(item);
    const factor = factorGuardado > 0
      ? factorGuardado
      : (factorBase > 0 ? factorBase : 1);

    if (!item) return;

    const clave =
      claveFecha_(fecha) + '|' +
      normalizar_(puntoVenta) + '|' +
      item;

    if (!agrupados.has(clave)) {
      agrupados.set(clave, {
        fecha: fecha,
        puntoVenta: puntoVenta,
        item: item,
        producto: producto,
        udm: udm,
        cerrado: 0,
        abierto: 0,
        factor: factor
      });
    }

    const registro = agrupados.get(clave);
    registro.cerrado += cerrado;
    registro.abierto += abierto;
  });

  const fechaActualizacion = new Date();
  const filasResumen = [...agrupados.values()]
    .sort((a, b) => {
      const porFecha = claveFecha_(a.fecha)
        .localeCompare(claveFecha_(b.fecha));
      if (porFecha !== 0) return porFecha;
      return String(a.item).localeCompare(
        String(b.item),
        'es',
        { numeric: true }
      );
    })
    .map(registro => [
      registro.fecha,
      registro.puntoVenta,
      registro.item,
      registro.producto,
      registro.udm,
      registro.cerrado,
      registro.abierto,
      registro.factor,
      (registro.cerrado * registro.factor) + registro.abierto,
      fechaActualizacion
    ]);

  hojaResumen.clearContents();
  hojaResumen.getRange(1, 1, 1, encabezados.length)
    .setValues([encabezados]);

  if (filasResumen.length > 0) {
    hojaResumen
      .getRange(
        2,
        1,
        filasResumen.length,
        encabezados.length
      )
      .setValues(filasResumen);
  }

  aplicarFormatoResumen_(hojaResumen, encabezados.length);
}


function registrarEnResumenGeneral_(filasNuevas) {
  const libroGeneral = SpreadsheetApp.openByUrl(URL_RESUMEN_GENERAL);
  const hoja = obtenerHojaResumenGeneral_(libroGeneral);
  const encabezados = encabezadosResumenGeneral_();

  prepararHojaResumenGeneral_(hoja, encabezados);

  const ultimaFila = hoja.getLastRow();
  const existentes = ultimaFila < 2
    ? []
    : hoja.getRange(2, 1, ultimaFila - 1, encabezados.length).getValues();
  const filaPorClave = new Map();

  existentes.forEach((fila, indice) => {
    const clave = claveResumenGeneral_(fila[0], fila[1], fila[2]);
    if (clave) filaPorClave.set(clave, indice + 2);
  });

  const nuevosAgrupados = new Map();

  filasNuevas.forEach(fila => {
    agregarRegistroResumen_(nuevosAgrupados, {
      fecha: fila[2],
      puntoVenta: fila[3],
      item: fila[5],
      producto: fila[6],
      udm: fila[7],
      cerrado: fila[8],
      abierto: fila[9],
      factor: fila[10],
      conteoFisico: fila[11]
    });
  });

  const fechaActualizacion = new Date();
  const filasParaAgregar = [];

  nuevosAgrupados.forEach((registro, clave) => {
    const numeroFila = filaPorClave.get(clave);

    if (numeroFila) {
      const anterior = existentes[numeroFila - 2];
      const cerrado = (Number(anterior[5]) || 0) + registro.cerrado;
      const abierto = (Number(anterior[6]) || 0) + registro.abierto;
      const conteoFisico =
        (Number(anterior[8]) || 0) + registro.conteoFisico;

      hoja.getRange(numeroFila, 1, 1, encabezados.length).setValues([[
        registro.fecha,
        registro.puntoVenta,
        registro.item,
        registro.producto,
        registro.udm,
        cerrado,
        abierto,
        registro.factor,
        conteoFisico,
        fechaActualizacion
      ]]);
    } else {
      filasParaAgregar.push([
        registro.fecha,
        registro.puntoVenta,
        registro.item,
        registro.producto,
        registro.udm,
        registro.cerrado,
        registro.abierto,
        registro.factor,
        registro.conteoFisico,
        fechaActualizacion
      ]);
    }
  });

  if (filasParaAgregar.length > 0) {
    hoja.getRange(
      hoja.getLastRow() + 1,
      1,
      filasParaAgregar.length,
      encabezados.length
    ).setValues(filasParaAgregar);
  }

  aplicarFormatoResumen_(hoja, encabezados.length);
}


function reconstruirResumenGeneral() {
  const libroMaestro = obtenerLibroMaestro_();
  const control = libroMaestro.getSheetByName('Control Formularios');

  if (!control || control.getLastRow() < 2) {
    throw new Error('No se encontró la hoja Control Formularios.');
  }

  const registrosControl = control
    .getRange(2, 1, control.getLastRow() - 1, 4)
    .getDisplayValues();
  const agrupados = new Map();

  registrosControl.forEach(registroControl => {
    const puntoVenta = String(registroControl[1] || '').trim();
    const estado = String(registroControl[2] || '').trim().toUpperCase();
    const url = String(registroControl[3] || '').trim();

    if (!puntoVenta || estado !== 'LISTO' || !url) return;

    const libroPDV = SpreadsheetApp.openByUrl(url);
    const hojaConteos = libroPDV.getSheetByName('Conteos Inventarios');

    if (!hojaConteos || hojaConteos.getLastRow() < 2) return;

    const datos = hojaConteos
      .getRange(1, 1, hojaConteos.getLastRow(), hojaConteos.getLastColumn())
      .getValues();
    const encabezados = datos[0].map(normalizar_);
    const indice = opciones => buscarIndice_(encabezados, opciones);
    const cFecha = indice(['fecha inventario']);
    const cPDV = indice(['punto de venta', 'pdv']);
    const cItem = indice(['item', 'codigo', 'cod']);
    const cProducto = indice(['nombre producto', 'producto']);
    const cUDM = indice(['desc u m', 'desc um', 'udm', 'unidad de medida']);
    const cCerrado = indice(['cerrado']);
    const cAbierto = indice(['abierto']);
    const cFactor = indice(['factor', 'factor um', 'factor u m', 'factor udm']);
    const cFisico = indice(['conteo fisico', 'conteofisico']);
    const factores = obtenerFactoresPorItem_(libroPDV);

    datos.slice(1).forEach(fila => {
      const item = String(fila[cItem] || '').trim();
      if (!item) return;

      const cerrado = Number(fila[cCerrado]) || 0;
      const abierto = Number(fila[cAbierto]) || 0;
      const factorGuardado = cFactor === -1
        ? NaN
        : obtenerFactorCorrecto_(fila[cUDM], fila[cFactor]);
      const factorBase = factores.get(item);
      const factor = factorGuardado > 0
        ? factorGuardado
        : (factorBase > 0 ? factorBase : 1);
      const conteoFisico = (cerrado * factor) + abierto;

      agregarRegistroResumen_(agrupados, {
        fecha: fila[cFecha],
        puntoVenta: cPDV === -1 ? puntoVenta : fila[cPDV],
        item: item,
        producto: fila[cProducto],
        udm: fila[cUDM],
        cerrado: cerrado,
        abierto: abierto,
        factor: factor,
        conteoFisico: conteoFisico
      });
    });
  });

  const libroGeneral = SpreadsheetApp.openByUrl(URL_RESUMEN_GENERAL);
  const hoja = obtenerHojaResumenGeneral_(libroGeneral);
  const encabezados = encabezadosResumenGeneral_();
  const fechaActualizacion = new Date();
  const filas = [...agrupados.values()]
    .sort((a, b) => {
      const porFecha = claveFecha_(a.fecha).localeCompare(claveFecha_(b.fecha));
      if (porFecha !== 0) return porFecha;
      const porPDV = String(a.puntoVenta).localeCompare(String(b.puntoVenta), 'es');
      if (porPDV !== 0) return porPDV;
      return String(a.item).localeCompare(String(b.item), 'es', { numeric: true });
    })
    .map(registro => [
      registro.fecha,
      registro.puntoVenta,
      registro.item,
      registro.producto,
      registro.udm,
      registro.cerrado,
      registro.abierto,
      registro.factor,
      registro.conteoFisico,
      fechaActualizacion
    ]);

  hoja.clearContents();
  hoja.getRange(1, 1, 1, encabezados.length).setValues([encabezados]);

  if (filas.length > 0) {
    hoja.getRange(2, 1, filas.length, encabezados.length).setValues(filas);
  }

  aplicarFormatoResumen_(hoja, encabezados.length);
  return 'Resumen general reconstruido: ' + filas.length + ' registros.';
}


function agregarRegistroResumen_(mapa, registro) {
  const clave = claveResumenGeneral_(
    registro.fecha,
    registro.puntoVenta,
    registro.item
  );

  if (!clave) return;

  if (!mapa.has(clave)) {
    mapa.set(clave, {
      fecha: registro.fecha,
      puntoVenta: registro.puntoVenta,
      item: String(registro.item || '').trim(),
      producto: registro.producto,
      udm: registro.udm,
      cerrado: 0,
      abierto: 0,
      factor: Number(registro.factor) || 1,
      conteoFisico: 0
    });
  }

  const acumulado = mapa.get(clave);
  acumulado.cerrado += Number(registro.cerrado) || 0;
  acumulado.abierto += Number(registro.abierto) || 0;
  acumulado.conteoFisico += Number(registro.conteoFisico) || 0;
}


function claveResumenGeneral_(fecha, puntoVenta, item) {
  const itemLimpio = String(item || '').trim();
  if (!itemLimpio) return '';

  return claveFecha_(fecha) + '|' +
    normalizar_(puntoVenta) + '|' + itemLimpio;
}


function encabezadosResumenGeneral_() {
  return [
    'Fecha inventario',
    'Punto de venta',
    'Item',
    'Descripcionproducto',
    'UDM',
    'Cerrado',
    'Abierto',
    'Factor',
    'ConteoFisico',
    'Última actualización'
  ];
}


function obtenerHojaResumenGeneral_(libro) {
  let hoja = libro.getSheetByName('Resumen General');
  if (hoja) return hoja;

  const primeraHoja = libro.getSheets()[0];
  if (primeraHoja && primeraHoja.getLastRow() === 0) {
    primeraHoja.setName('Resumen General');
    return primeraHoja;
  }

  return libro.insertSheet('Resumen General');
}


function prepararHojaResumenGeneral_(hoja, encabezados) {
  if (hoja.getLastRow() === 0) {
    hoja.getRange(1, 1, 1, encabezados.length).setValues([encabezados]);
  }
}


function obtenerFactoresPorItem_(libroPDV) {
  const factores = new Map();
  const hoja = buscarHoja_(libroPDV, 'Uno a Uno');

  if (!hoja || hoja.getLastRow() < 2) {
    return factores;
  }

  const datos = hoja
    .getRange(1, 1, hoja.getLastRow(), hoja.getLastColumn())
    .getValues();
  const encabezados = datos[0].map(normalizar_);
  const columnaItem = buscarIndice_(
    encabezados,
    ['item', 'codigo', 'cod', 'id producto']
  );
  const columnaFactor = buscarIndice_(
    encabezados,
    ['factor', 'factor um', 'factor u m', 'factor udm']
  );
  const columnaUDM = buscarIndice_(
    encabezados,
    ['desc u m', 'desc um', 'udm', 'unidad de medida', 'unidad']
  );

  if (columnaItem === -1 || columnaFactor === -1) {
    return factores;
  }

  datos.slice(1).forEach(fila => {
    const item = String(fila[columnaItem] || '').trim();
    const udm = columnaUDM === -1 ? '' : fila[columnaUDM];
    const factor = obtenerFactorCorrecto_(udm, fila[columnaFactor]);

    if (item && factor > 0) {
      factores.set(item, factor);
    }
  });

  return factores;
}


function convertirNumero_(valor, valorVacio) {
  if (valor === '' || valor === null || valor === undefined) {
    return valorVacio;
  }

  return Number(String(valor).replace(',', '.'));
}


function normalizarFactor_(valor, valorVacio) {
  let factor = convertirNumero_(valor, valorVacio);

  if (!isFinite(factor)) return valorVacio;

  // Los factores importados quedaron multiplicados por 10.000.
  while (factor >= 10000) factor /= 10000;
  return factor;
}


function obtenerFactorCorrecto_(descripcionUDM, factorGuardado) {
  const texto = String(descripcionUDM || '').trim();
  const coincidencia = texto.match(/^x\s*(\d+(?:[.,]\d+)?)/i);

  if (coincidencia) {
    const factorDescripcion = Number(coincidencia[1].replace(',', '.'));
    if (factorDescripcion > 0) return factorDescripcion;
  }

  const factorNormalizado = normalizarFactor_(factorGuardado, 1);
  return factorNormalizado > 0 ? factorNormalizado : 1;
}


function aplicarFormatoResumen_(hojaResumen, cantidadColumnas) {
  hojaResumen
    .getRange(1, 1, 1, cantidadColumnas)
    .setBackground('#4A2B14')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold');

  hojaResumen.setFrozenRows(1);
  hojaResumen.autoResizeColumns(1, cantidadColumnas);
}


function claveFecha_(valor) {
  if (valor instanceof Date && !isNaN(valor.getTime())) {
    return Utilities.formatDate(
      valor,
      Session.getScriptTimeZone(),
      'yyyy-MM-dd'
    );
  }

  const texto = String(valor || '').trim();

  if (/^\d{4}-\d{2}-\d{2}$/.test(texto)) {
    return texto;
  }

  const partes = texto.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);

  if (partes) {
    return partes[3] + '-' +
      String(partes[2]).padStart(2, '0') + '-' +
      String(partes[1]).padStart(2, '0');
  }

  return texto;
}


function obtenerLibroPDV_(puntoVenta) {
  const libroMaestro = obtenerLibroMaestro_();
  const control = libroMaestro.getSheetByName('Control Formularios');

  if (!control || control.getLastRow() < 2) {
    throw new Error('No se encontró la hoja Control Formularios.');
  }

  const registros = control
    .getRange(2, 1, control.getLastRow() - 1, 4)
    .getDisplayValues();

  const registro = registros.find(fila =>
    fila[1].trim() === puntoVenta &&
    fila[2].trim().toUpperCase() === 'LISTO' &&
    fila[3] !== ''
  );

  if (!registro) {
    throw new Error(
      'No se encontró la base disponible para ' + puntoVenta + '.'
    );
  }

  return SpreadsheetApp.openByUrl(registro[3]);
}


function buscarHoja_(libro, nombreBuscado) {
  const nombreNormalizado = normalizar_(nombreBuscado);

  return libro.getSheets().find(hoja =>
    normalizar_(hoja.getName()) === nombreNormalizado
  ) || null;
}


function buscarIndice_(encabezados, opciones) {
  const opcionesNormalizadas = opciones.map(normalizar_);

  return encabezados.findIndex(encabezado =>
    opcionesNormalizadas.includes(encabezado)
  );
}


function normalizar_(texto) {
  return String(texto || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[.\-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}


function actualizarTodasLasBasesUDM() {
  const libroMaestro = obtenerLibroMaestro_();
  const hojaMaestra =
    libroMaestro.getSheetByName('Base de datos UDM');

  if (!hojaMaestra || hojaMaestra.getLastRow() < 2) {
    throw new Error(
      'No se encontró información en la hoja Base de datos UDM.'
    );
  }

  const datosMaestros = hojaMaestra
    .getRange(2, 1, hojaMaestra.getLastRow() - 1, 5)
    .getValues();

  const productosMaestros = new Map();

  datosMaestros.forEach(fila => {
    const nombreProducto = normalizar_(fila[1]);

    if (nombreProducto !== '') {
      productosMaestros.set(nombreProducto, {
        descripcionUDM: String(fila[2] || '').trim(),
        factorUDM: obtenerFactorCorrecto_(fila[2], fila[3])
      });
    }
  });

  const hojaControl =
    libroMaestro.getSheetByName('Control Formularios');

  if (!hojaControl || hojaControl.getLastRow() < 2) {
    throw new Error('No se encontró la hoja Control Formularios.');
  }

  const registros = hojaControl
    .getRange(2, 1, hojaControl.getLastRow() - 1, 4)
    .getDisplayValues();

  const resultados = [];

  registros.forEach(fila => {
    const puntoVenta = String(fila[1] || '').trim();
    const estado = String(fila[2] || '').trim().toUpperCase();
    const url = String(fila[3] || '').trim();

    if (!puntoVenta || estado !== 'LISTO' || !url) return;

    try {
      const libroPDV = SpreadsheetApp.openByUrl(url);
      const hojaUnoAUno = buscarHoja_(libroPDV, 'Uno a Uno');

      if (!hojaUnoAUno || hojaUnoAUno.getLastRow() < 2) {
        throw new Error('No tiene productos en la hoja Uno a Uno.');
      }

      const ultimaFila = hojaUnoAUno.getLastRow();
      let ultimaColumna = hojaUnoAUno.getLastColumn();
      let encabezados = hojaUnoAUno
        .getRange(1, 1, 1, ultimaColumna)
        .getDisplayValues()[0]
        .map(normalizar_);

      const columnaProducto = buscarIndice_(
        encabezados,
        ['nombre producto', 'producto', 'descripcion', 'desc item']
      );

      if (columnaProducto === -1) {
        throw new Error('No se encontró la columna del producto.');
      }

      let columnaUDM = buscarIndice_(
        encabezados,
        ['desc u m', 'desc um', 'udm', 'unidad de medida', 'unidad']
      );

      if (columnaUDM === -1) {
        ultimaColumna++;
        hojaUnoAUno.getRange(1, ultimaColumna).setValue('Desc. U.M.');
        columnaUDM = ultimaColumna - 1;
      } else {
        hojaUnoAUno.getRange(1, columnaUDM + 1).setValue('Desc. U.M.');
      }

      ultimaColumna = hojaUnoAUno.getLastColumn();
      encabezados = hojaUnoAUno
        .getRange(1, 1, 1, ultimaColumna)
        .getDisplayValues()[0]
        .map(normalizar_);

      let columnaFactor = buscarIndice_(
        encabezados,
        ['factor', 'factor um', 'factor u m', 'factor udm']
      );

      if (columnaFactor === -1) {
        ultimaColumna++;
        hojaUnoAUno.getRange(1, ultimaColumna).setValue('Factor U.M.');
        columnaFactor = ultimaColumna - 1;
      }

      const cantidadFilas = ultimaFila - 1;
      const nombres = hojaUnoAUno
        .getRange(2, columnaProducto + 1, cantidadFilas, 1)
        .getDisplayValues();
      const valoresUDM = hojaUnoAUno
        .getRange(2, columnaUDM + 1, cantidadFilas, 1)
        .getValues();
      const valoresFactor = hojaUnoAUno
        .getRange(2, columnaFactor + 1, cantidadFilas, 1)
        .getValues();

      let actualizados = 0;
      const sinCoincidencia = [];

      nombres.forEach((filaProducto, indice) => {
        const nombreOriginal = String(filaProducto[0] || '').trim();
        const maestro = productosMaestros.get(normalizar_(nombreOriginal));

        if (maestro) {
          valoresUDM[indice][0] = maestro.descripcionUDM;
          valoresFactor[indice][0] = maestro.factorUDM;
          actualizados++;
        } else if (nombreOriginal) {
          sinCoincidencia.push(nombreOriginal);
        }
      });

      hojaUnoAUno
        .getRange(2, columnaUDM + 1, cantidadFilas, 1)
        .setValues(valoresUDM);
      hojaUnoAUno
        .getRange(2, columnaFactor + 1, cantidadFilas, 1)
        .setValues(valoresFactor);

      resultados.push([
        new Date(),
        puntoVenta,
        'ACTUALIZADO',
        actualizados,
        sinCoincidencia.length,
        sinCoincidencia.slice(0, 20).join(' | ')
      ]);
    } catch (error) {
      resultados.push([
        new Date(), puntoVenta, 'ERROR', 0, 0, error.message
      ]);
    }
  });

  let hojaResultados =
    libroMaestro.getSheetByName('Registro actualización UDM');

  if (!hojaResultados) {
    hojaResultados =
      libroMaestro.insertSheet('Registro actualización UDM');
  }

  if (hojaResultados.getLastRow() === 0) {
    hojaResultados.appendRow([
      'Fecha y hora',
      'Punto de venta',
      'Estado',
      'Productos actualizados',
      'Productos sin coincidencia',
      'Detalle'
    ]);

    hojaResultados
      .getRange(1, 1, 1, 6)
      .setBackground('#4A2B14')
      .setFontColor('#FFFFFF')
      .setFontWeight('bold');
  }

  if (resultados.length > 0) {
    hojaResultados
      .getRange(
        hojaResultados.getLastRow() + 1,
        1,
        resultados.length,
        6
      )
      .setValues(resultados);
  }

  SpreadsheetApp.flush();

  return 'Proceso terminado. Se revisaron ' +
    resultados.length + ' puntos de venta.';
}
