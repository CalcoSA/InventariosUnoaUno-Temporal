async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || (data && data.correcto === false)) {
    throw new Error(data.mensaje || 'Ocurrió un error inesperado.');
  }
  return data;
}

    let productos = [];
    let puntoVentaActual = '';
    let fechaActual = '';
    let categoriaActual = '';

    document.addEventListener(
      'DOMContentLoaded',
      function () {
        asignarFechaActual();
        cargarPuntosVenta();
      }
    );

    function asignarFechaActual() {
      const hoy = new Date();
      const anio = hoy.getFullYear();

      const mes = String(
        hoy.getMonth() + 1
      ).padStart(2, '0');

      const dia = String(
        hoy.getDate()
      ).padStart(2, '0');

      document
        .getElementById('fechaInventario')
        .value =
          anio + '-' + mes + '-' + dia;
    }

    function cargarPuntosVenta() {
      fetchJSON('/api/puntos-venta')
        .then(function (puntos) {
          const selector =
            document.getElementById('puntoVenta');

          selector.innerHTML =
            '<option value="">' +
            'Seleccione un punto de venta' +
            '</option>';

          puntos.forEach(function (punto) {
            const opcion =
              document.createElement('option');

            opcion.value = punto;
            opcion.textContent = punto;
            selector.appendChild(opcion);
          });

          if (puntos.length === 0) {
            mostrarMensaje(
              'mensajeInicio',
              'No se encontraron puntos de venta disponibles.',
              'error'
            );
          }
        })
        .catch(function (error) {
          mostrarMensaje(
            'mensajeInicio',
            obtenerMensajeError(error),
            'error'
          );
        });
    }

    function cargarCategoriasPDV() {
      const puntoVenta =
        document
          .getElementById('puntoVenta')
          .value;

      const selector =
        document
          .getElementById('categoriaInventario');

      ocultarMensaje('mensajeInicio');
      selector.disabled = true;

      if (!puntoVenta) {
        selector.innerHTML =
          '<option value="">' +
          'Seleccione primero el PDV' +
          '</option>';

        return;
      }

      selector.innerHTML =
        '<option value="">' +
        'Cargando categorías...' +
        '</option>';

      fetchJSON('/api/categorias?' + new URLSearchParams({pdv: puntoVenta}))
        .then(function (categorias) {
          selector.innerHTML =
            '<option value="">' +
            'Seleccione una categoría' +
            '</option>';

          categorias.forEach(function (categoria) {
            const opcion =
              document.createElement('option');

            opcion.value = categoria;
            opcion.textContent = categoria;
            selector.appendChild(opcion);
          });

          selector.disabled = false;

          if (categorias.length === 0) {
            mostrarMensaje(
              'mensajeInicio',
              'No se encontraron categorías para este PDV.',
              'error'
            );
          }
        })
        .catch(function (error) {
          selector.innerHTML =
            '<option value="">' +
            'No fue posible cargar' +
            '</option>';

          mostrarMensaje(
            'mensajeInicio',
            obtenerMensajeError(error),
            'error'
          );
        });
    }

    function comenzarInventario() {
      const puntoVenta =
        document
          .getElementById('puntoVenta')
          .value;

      const fecha =
        document
          .getElementById('fechaInventario')
          .value;

      const categoria =
        document
          .getElementById('categoriaInventario')
          .value;

      ocultarMensaje('mensajeInicio');

      if (!puntoVenta || !fecha || !categoria) {
        mostrarMensaje(
          'mensajeInicio',
          'Seleccione el punto de venta, la fecha y la categoría.',
          'error'
        );

        return;
      }

      puntoVentaActual = puntoVenta;
      fechaActual = fecha;
      categoriaActual = categoria;

      document
        .getElementById('pantallaInicio')
        .classList.add('oculto');

      document
        .getElementById('pantallaCarga')
        .classList.remove('oculto');

      fetchJSON('/api/productos?' + new URLSearchParams({pdv: puntoVentaActual, categoria: categoriaActual}))
        .then(function (lista) {
          document
            .getElementById('pantallaCarga')
            .classList.add('oculto');

          if (!lista || lista.length === 0) {
            document
              .getElementById('pantallaInicio')
              .classList.remove('oculto');

            mostrarMensaje(
              'mensajeInicio',
              'La categoría seleccionada no contiene productos.',
              'error'
            );

            return;
          }

          productos = lista.map(function (producto) {
            producto.cerrado = '';
            producto.abierto = '';

            return producto;
          });

          recuperarBorrador();
          prepararInventario();

          document
            .getElementById('pantallaInventario')
            .classList.remove('oculto');
        })
        .catch(function (error) {
          document
            .getElementById('pantallaCarga')
            .classList.add('oculto');

          document
            .getElementById('pantallaInicio')
            .classList.remove('oculto');

          mostrarMensaje(
            'mensajeInicio',
            obtenerMensajeError(error),
            'error'
          );
        });
    }

    function prepararInventario() {
      document
        .getElementById('nombrePDV')
        .textContent = puntoVentaActual;

      document
        .getElementById('fechaResumen')
        .textContent =
          'Fecha: ' +
          formatearFecha(fechaActual);

      document
        .getElementById('categoriaResumen')
        .textContent =
          'Categoría: ' + categoriaActual;

      document
        .getElementById('buscador')
        .value = '';

      mostrarProductos();
      actualizarProgreso();
    }

    function mostrarProductos() {
      const texto = normalizarTexto(
        document
          .getElementById('buscador')
          .value
      );

      const resultados =
        productos.filter(function (producto) {
          const contenido = normalizarTexto(
            producto.item +
            ' ' +
            producto.producto
          );

          return contenido.includes(texto);
        });

      const contenedor =
        document.getElementById('listaProductos');

      if (resultados.length === 0) {
        contenedor.innerHTML =
          '<div class="sin-resultados">' +
          'No se encontraron productos con esa búsqueda.' +
          '</div>';

        return;
      }

      contenedor.innerHTML =
        resultados.map(function (producto) {
          const indice =
            productos.indexOf(producto);

          return `
            <article class="producto">
              <div>
                <span class="categoria">
                  ${escaparHTML(producto.categoria)}
                </span>

                <div class="nombre-producto">
                  ${escaparHTML(producto.producto)}
                </div>

                <div class="detalle-producto">
                  Código:
                  ${escaparHTML(producto.item)}
                  · Desc. U.M.:
                  ${escaparHTML(
                    producto.udm || 'Sin UDM'
                  )}
                </div>
              </div>

              <div class="cantidades">
                <div class="cantidad">
                  <label for="cerrado-${indice}">
                    Cerrado
                  </label>

                  <input
                    id="cerrado-${indice}"
                    type="number"
                    min="0"
                    step="any"
                    inputmode="decimal"
                    value="${escaparHTML(producto.cerrado)}"
                    oninput="registrarCantidad(
                      ${indice},
                      'cerrado',
                      this.value
                    )"
                    placeholder="0"
                  >
                </div>

                <div class="cantidad">
                  <label for="abierto-${indice}">
                    Abierto
                  </label>

                  <input
                    id="abierto-${indice}"
                    type="number"
                    min="0"
                    step="any"
                    inputmode="decimal"
                    value="${escaparHTML(producto.abierto)}"
                    oninput="registrarCantidad(
                      ${indice},
                      'abierto',
                      this.value
                    )"
                    placeholder="0"
                  >
                </div>
              </div>
            </article>
          `;
        }).join('');
    }

    function registrarCantidad(
      indice,
      tipo,
      valor
    ) {
      productos[indice][tipo] = valor;

      guardarBorrador();
      actualizarProgreso();
    }

    function actualizarProgreso() {
      const completados =
        productos.filter(function (producto) {
          return (
            producto.cerrado !== '' &&
            producto.abierto !== ''
          );
        }).length;

      const total = productos.length;

      const porcentaje = total
        ? Math.round(
            (completados / total) * 100
          )
        : 0;

      document
        .getElementById('textoProgreso')
        .textContent =
          completados +
          ' de ' +
          total +
          ' (' +
          porcentaje +
          '%)';

      document
        .getElementById('barraProgreso')
        .style.width =
          porcentaje + '%';
    }

    function completarVaciosConCero() {
      const cantidadVacios =
        productos.reduce(
          function (total, producto) {
            return (
              total +
              (producto.cerrado === '' ? 1 : 0) +
              (producto.abierto === '' ? 1 : 0)
            );
          },
          0
        );

      if (cantidadVacios === 0) {
        return;
      }

      const confirmar = window.confirm(
        'Se marcarán ' +
        cantidadVacios +
        ' casillas vacías con valor 0. ' +
        '¿Desea continuar?'
      );

      if (!confirmar) {
        return;
      }

      productos.forEach(function (producto) {
        if (producto.cerrado === '') {
          producto.cerrado = '0';
        }

        if (producto.abierto === '') {
          producto.abierto = '0';
        }
      });

      guardarBorrador();
      mostrarProductos();
      actualizarProgreso();
    }

    function guardarInventario() {
      ocultarMensaje('mensajeInventario');

      const pendientes =
        productos.filter(function (producto) {
          return (
            producto.cerrado === '' ||
            producto.abierto === ''
          );
        }).length;

      if (pendientes > 0) {
        mostrarMensaje(
          'mensajeInventario',
          'Faltan ' +
          pendientes +
          ' productos por completar. ' +
          'Registre Cerrado y Abierto o utilice ' +
          '“Completar vacíos con 0”.',
          'error'
        );

        return;
      }

      const confirmar = window.confirm(
        '¿Confirma que desea guardar la categoría ' +
        categoriaActual +
        ' de ' +
        puntoVentaActual +
        '?'
      );

      if (!confirmar) {
        return;
      }

      const boton =
        document.getElementById('botonGuardar');

      boton.disabled = true;
      boton.textContent =
        'Guardando inventario...';

      const datos = {
        puntoVenta: puntoVentaActual,
        fecha: fechaActual,
        categoria: categoriaActual,

        conteos: productos.map(
          function (producto) {
            return {
              categoria: producto.categoria,
              item: producto.item,
              producto: producto.producto,
              udm: producto.udm,
              cerrado: producto.cerrado,
              abierto: producto.abierto
            };
          }
        )
      };

      fetchJSON('/api/inventarios', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(datos)})
        .then(function () {
          eliminarBorrador();

          document
            .getElementById('pantallaInventario')
            .classList.add('oculto');

          document
            .getElementById('pantallaExito')
            .classList.remove('oculto');

          boton.disabled = false;
          boton.textContent =
            'Guardar inventario';
        })
        .catch(function (error) {
          boton.disabled = false;
          boton.textContent =
            'Guardar inventario';

          mostrarMensaje(
            'mensajeInventario',
            obtenerMensajeError(error),
            'error'
          );

          window.scrollTo({
            top: 0,
            behavior: 'smooth'
          });
        });
    }

    function nuevoInventario() {
      productos = [];
      puntoVentaActual = '';
      fechaActual = '';
      categoriaActual = '';

      document
        .getElementById('puntoVenta')
        .value = '';

      const selectorCategoria =
        document
          .getElementById('categoriaInventario');

      selectorCategoria.innerHTML =
        '<option value="">' +
        'Seleccione primero el PDV' +
        '</option>';

      selectorCategoria.disabled = true;

      asignarFechaActual();

      document
        .getElementById('pantallaExito')
        .classList.add('oculto');

      document
        .getElementById('pantallaInicio')
        .classList.remove('oculto');

      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    }

    function guardarBorrador() {
      try {
        localStorage.setItem(
          obtenerClaveBorrador(),

          JSON.stringify(
            productos.map(function (producto) {
              return {
                item: producto.item,
                cerrado: producto.cerrado,
                abierto: producto.abierto
              };
            })
          )
        );
      } catch (error) {
        console.log(
          'No se pudo guardar el borrador.'
        );
      }
    }

    function recuperarBorrador() {
      try {
        const borrador = JSON.parse(
          localStorage.getItem(
            obtenerClaveBorrador()
          ) || '[]'
        );

        const cantidades = {};

        borrador.forEach(function (registro) {
          cantidades[String(registro.item)] = {
            cerrado: registro.cerrado,
            abierto: registro.abierto
          };
        });

        productos.forEach(function (producto) {
          const clave = String(producto.item);

          if (
            Object.prototype.hasOwnProperty.call(
              cantidades,
              clave
            )
          ) {
            const conteo = cantidades[clave];

            producto.cerrado =
              conteo.cerrado === undefined
                ? ''
                : conteo.cerrado;

            producto.abierto =
              conteo.abierto === undefined
                ? ''
                : conteo.abierto;
          }
        });
      } catch (error) {
        console.log(
          'No se pudo recuperar el borrador.'
        );
      }
    }

    function eliminarBorrador() {
      try {
        localStorage.removeItem(
          obtenerClaveBorrador()
        );
      } catch (error) {
        console.log(
          'No se pudo eliminar el borrador.'
        );
      }
    }

    function obtenerClaveBorrador() {
      return (
        'inventario-uno-a-uno-v3-' +
        puntoVentaActual +
        '-' +
        fechaActual +
        '-' +
        categoriaActual
      );
    }

    function mostrarMensaje(
      id,
      texto,
      tipo
    ) {
      const elemento =
        document.getElementById(id);

      elemento.textContent = texto;
      elemento.className =
        'mensaje ' + tipo;
    }

    function ocultarMensaje(id) {
      const elemento =
        document.getElementById(id);

      elemento.textContent = '';
      elemento.className = 'mensaje';
    }

    function obtenerMensajeError(error) {
      return error && error.message
        ? error.message
        : String(
            error ||
            'Ocurrió un error inesperado.'
          );
    }

    function formatearFecha(fecha) {
      const partes = fecha.split('-');

      if (partes.length !== 3) {
        return fecha;
      }

      return (
        partes[2] +
        '/' +
        partes[1] +
        '/' +
        partes[0]
      );
    }

    function normalizarTexto(texto) {
      return String(texto || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
    }

    function escaparHTML(valor) {
      return String(valor ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }
  
