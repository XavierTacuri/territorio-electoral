import { SimpleDatasetImportPage } from './SimpleDatasetImportPage';

export const POLLING_PLACE_HEADERS = [
  'process_code',
  'province_dpa',
  'canton_dpa',
  'parish_dpa',
  'polling_place_code',
  'polling_place_name',
  'polling_place_address',
  'polling_place_latitude',
  'polling_place_longitude',
] as const;

export default function PollingPlaceImportPage() {
  return (
    <SimpleDatasetImportPage
      title="Recintos electorales"
      description="Importación oficial de recintos electorales (Modo Jornada Electoral). Ubicación cartográfica opcional."
      datasetType="CNE_POLLING_PLACES"
      mappingProfile="CANONICAL_POLLING_PLACE"
      headers={POLLING_PLACE_HEADERS}
      successMessage="Recintos importados correctamente."
    />
  );
}
