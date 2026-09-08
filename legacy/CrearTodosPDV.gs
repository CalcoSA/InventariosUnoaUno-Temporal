const MIME_XLSX_PDV =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function iniciarCreacionMasiva() {
  const maestro = SpreadsheetApp.getActiveSpreadsheet();
  const padres = DriveApp.getFileById(maestro.getId()).getParents();

  if (!padres.hasNext()) {
    throw new Error('No se encontró la carpeta de los formatos.');
  }

  const carpeta = padres.next();
  const propiedades = PropertiesService.getScriptProperties();

  propiedades.setProperty('MAESTRO_ID', maestro.getId());
  propiedades.setProperty('CARPETA_ID', carpeta.getId());

  let control = maestro.getSheetByName('Control Formularios');

  if (!control) {
    control = maestro.insertSheet('Control Formularios');
    control.getRange('A1:I1').setValues([[
      'ID archivo',
      'Punto de venta',
      'Estado',
      'Base Google Sheets',
      'Formulario para responder',
      'Formulario para editar',
      'Productos',
      'Fecha',
      'Detalle'
    ]]);

    control.setFrozenRows(1);
  }

  registrarBC01_(maestro, carpeta, control);

  control.getRange('K1:L3').setValues([
    ['Proceso', 'Creación de formularios'],
    ['Estado general', 'EN PROCESO'],
    ['Última revisión', new Date()]
  ]);

  eliminarTriggersPDV_();
  procesarSiguientePDV();
}

function procesarSiguientePDV() {
  eliminarTriggersPDV_();

  const propiedades = PropertiesService.getScriptProperties();
  const maestroId = propiedades.getProperty('MAESTRO_ID');
  const carpetaId = propiedades.getProperty('CARPETA_ID');

  if (!maestroId || !carpetaId) {
    throw new Error('Primero debes ejecutar iniciarCreacionMasiva.');
  }

  const maestro = SpreadsheetApp.openById(maestroId);
  const carpeta = DriveApp.getFolderById(carpetaId);
  const control = maestro.getSheetByName('Control Formularios');

  const procesados = new Set();

  if (control.getLastRow() > 1) {
    control
      .getRange(2, 1, control.getLastRow() - 1, 1)
      .getValues()
      .flat()
      .filter(String)
      .forEach(id => procesados.add(String(id)));
  }

  const nombreMaestro = quitarExtension_(maestro.getName());
  const archivos = carpeta.getFiles();
  let archivoPendiente = null;

  while (archivos.hasNext()) {
    const archivo = archivos.next();

    if (
      archivo.getMimeType() === MIME_XLSX_PDV &&
      quitarExtension_(archivo.getName()) !== nombreMaestro &&
      !procesados.has(archivo.getId())
    ) {
      archivoPendiente = archivo;
      break;
    }
  }

  if (!archivoPendiente) {
    control.getRange('L2:L3').setValues([
      ['FINALIZADO'],
      [new Date()]
    ]);
    return;
  }

  const filaControl = control.getLastRow() + 1;

  control.getRange(filaControl, 1, 1, 9).setValues([[
    archivoPendiente.getId(),
    quitarExtension_(archivoPendiente.getName()),
    'PROCESANDO',
    '',
    '',
    '',
    '',
    new Date(),
    ''
  ]]);

  SpreadsheetApp.flush();

  try {
    const nombrePDV = quitarExtension_(archivoPendiente.getName());

    const convertido = Drive.Files.create(
      {
        name: nombrePDV,
        mimeType: 'application/vnd.google-apps.spreadsheet',
        parents: [carpetaId]
      },
      archivoPendiente.getBlob(),
      { fields: 'id,name' }
    );

    Utilities.sleep(3000);

    const libroPDV = SpreadsheetApp.openById(convertido.id);

    const hoja = libroPDV.getSheets().find(
      hojaActual =>
        normalizarTexto_(hojaActual.getName()) === 'uno a uno'
    );

    if (!hoja) {
      throw new Error('No se encontró la hoja Uno a Uno.');
    }

    if (hoja.getLastRow() < 2) {
      throw new Error('La hoja Uno a Uno no contiene productos.');
    }

    const datos = hoja
      .getRange(2, 1, hoja.getLastRow() - 1, 4)
      .getDisplayValues()
      .filter(fila => fila[1] !== '' && fila[2] !== '');

    const formulario = FormApp.create(
      'Inventario Uno a Uno – ' + nombrePDV
    );

    formulario
      .setDescription(
        'Por favor, registre las cantidades físicas encontradas durante el conteo y verifique cuidadosamente la información antes de enviar el formulario.'
      )
      .setConfirmationMessage(
        '¡Inventario registrado correctamente! Gracias por verificar la información.'
      )
      .setProgressBar(true);

    try {
      formulario.setPublished(true);
    } catch (error) {
      console.log('Publicación automática no disponible.');
    }

    formulario
      .addTextItem()
      .setTitle('Nombre de quien realiza el inventario')
      .setRequired(true);

    formulario
      .addDateItem()
      .setTitle('Fecha del inventario')
      .setRequired(true);

    agregarProductosMasivo_(formulario, datos);

    formulario.setDestination(
      FormApp.DestinationType.SPREADSHEET,
      libroPDV.getId()
    );

    DriveApp
      .getFileById(formulario.getId())
      .moveTo(carpeta);

    let configuracion = libroPDV.getSheetByName('Configuración');

    if (!configuracion) {
      configuracion = libroPDV.insertSheet('Configuración');
    }

    configuracion.clear();

    configuracion.getRange('A1:B4').setValues([
      ['Dato', 'Enlace'],
      ['Formulario para responder', formulario.getPublishedUrl()],
      ['Formulario para editar', formulario.getEditUrl()],
      ['Fecha de creación', new Date()]
    ]);

    configuracion.autoResizeColumns(1, 2);

    control.getRange(filaControl, 3, 1, 7).setValues([[
      'LISTO',
      libroPDV.getUrl(),
      formulario.getPublishedUrl(),
      formulario.getEditUrl(),
      datos.length,
      new Date(),
      ''
    ]]);

  } catch (error) {
    control.getRange(filaControl, 3).setValue('ERROR');
    control.getRange(filaControl, 8).setValue(new Date());
    control.getRange(filaControl, 9).setValue(error.message);
  }

  control.getRange('L3').setValue(new Date());

  ScriptApp
    .newTrigger('procesarSiguientePDV')
    .timeBased()
    .after(60 * 1000)
    .create();
}

function agregarProductosMasivo_(formulario, datos) {
  const validacion = FormApp
    .createTextValidation()
    .requireNumberGreaterThanOrEqualTo(0)
    .setHelpText('Ingrese 0 o una cantidad mayor.')
    .build();

  const categorias = {};

  datos.forEach(fila => {
    const categoria = fila[0] || 'Productos';

    if (!categorias[categoria]) {
      categorias[categoria] = [];
    }

    categorias[categoria].push({
      item: fila[1],
      producto: fila[2],
      udm: fila[3]
    });
  });

  Object.keys(categorias).forEach(categoria => {
    formulario
      .addPageBreakItem()
      .setTitle(categoria)
      .setHelpText(
        'Registre la cantidad física encontrada para cada producto.'
      );

    categorias[categoria].forEach(producto => {
      formulario
        .addTextItem()
        .setTitle(producto.item + ' – ' + producto.producto)
        .setHelpText('Unidad de medida: ' + producto.udm)
        .setRequired(true)
        .setValidation(validacion);
    });
  });
}

function registrarBC01_(maestro, carpeta, control) {
  const nombreMaestro = quitarExtension_(maestro.getName());
  const archivos = carpeta.getFiles();
  let archivoBC01 = null;

  while (archivos.hasNext()) {
    const archivo = archivos.next();

    if (
      archivo.getMimeType() === MIME_XLSX_PDV &&
      quitarExtension_(archivo.getName()) === nombreMaestro
    ) {
      archivoBC01 = archivo;
      break;
    }
  }

  if (!archivoBC01) return;

  const ids = control.getLastRow() > 1
    ? control.getRange(2, 1, control.getLastRow() - 1, 1)
        .getValues().flat().map(String)
    : [];

  if (ids.includes(archivoBC01.getId())) return;

  const configuracion = maestro.getSheetByName('Configuración');
  const hoja = maestro.getSheetByName('Uno a Uno');

  control.appendRow([
    archivoBC01.getId(),
    nombreMaestro,
    'LISTO',
    maestro.getUrl(),
    configuracion ? configuracion.getRange('B2').getValue() : '',
    configuracion ? configuracion.getRange('B3').getValue() : '',
    hoja ? hoja.getLastRow() - 1 : '',
    new Date(),
    'Formulario inicial'
  ]);
}

function quitarExtension_(nombre) {
  return nombre.replace(/\.xlsx$/i, '').trim();
}

function normalizarTexto_(texto) {
  return String(texto)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase();
}

function eliminarTriggersPDV_() {
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (
      trigger.getHandlerFunction() === 'procesarSiguientePDV'
    ) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}
