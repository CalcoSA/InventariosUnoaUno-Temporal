/** API executable: conserva exclusivamente operaciones FormApp sin paridad REST. */
function configurarCompatibilidadInventario(formId, spreadsheetId) {
  const formulario = FormApp.openById(formId);
  formulario
    .setConfirmationMessage('¡Inventario registrado correctamente! Gracias por verificar la información.')
    .setProgressBar(true);
  const validacion = FormApp.createTextValidation()
    .requireNumberGreaterThanOrEqualTo(0)
    .setHelpText('Ingrese 0 o una cantidad mayor.')
    .build();
  // La primera pregunta de texto es el nombre; el resto son cantidades.
  formulario.getItems(FormApp.ItemType.TEXT).slice(1).forEach(item => {
    item.asTextItem().setValidation(validacion);
  });
  formulario.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheetId);
  return {
    publishedUrl: formulario.getPublishedUrl(),
    editUrl: formulario.getEditUrl()
  };
}
