import { SimpleDatasetImportPage } from './SimpleDatasetImportPage';

export const ELECTORAL_BOARD_HEADERS = [
  'process_code',
  'polling_place_code',
  'board_code',
  'board_number',
  'sex_category',
  'registered_voters',
] as const;

export default function ElectoralBoardImportPage() {
  return (
    <SimpleDatasetImportPage
      title="Juntas receptoras del voto"
      description="Importación oficial de juntas receptoras del voto (Modo Jornada Electoral). Cada junta debe pertenecer a un recinto ya importado."
      datasetType="CNE_ELECTORAL_BOARDS"
      mappingProfile="CANONICAL_ELECTORAL_BOARD"
      headers={ELECTORAL_BOARD_HEADERS}
      helperNote="Los recintos deben importarse primero: cada fila requiere un polling_place_code existente para el mismo proceso electoral."
      successMessage="Juntas importadas correctamente."
    />
  );
}
