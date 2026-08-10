export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}
export const statusMessage = (status: number): string =>
  ({
    400: 'La solicitud no es válida.',
    401: 'Tu sesión ha finalizado.',
    403: 'No tienes permisos para esta acción.',
    404: 'El recurso no existe.',
    409: 'La operación entra en conflicto con los datos actuales.',
    410: 'El archivo ya no está disponible.',
    413: 'El archivo supera el tamaño permitido.',
    415: 'El formato del archivo no está permitido.',
    422: 'Revisa los campos indicados.',
    500: 'Ocurrió un error inesperado.',
    503: 'El servicio no está disponible.',
  })[status] ?? 'No se pudo completar la solicitud.';
