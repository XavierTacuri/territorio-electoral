export type ParishOption = {
  id: number;
  name: string;
  dpa_code?: string;
  parish_type?: 'URBAN' | 'RURAL' | string;
};

function territorialType(parish: ParishOption) {
  if (parish.dpa_code?.endsWith('50')) return 'Cabecera cantonal';
  return parish.parish_type === 'RURAL' ? 'Rural' : 'Urbana';
}

export function parishOptionLabel(parish: ParishOption, options: ParishOption[]) {
  const ambiguous =
    options.filter(
      (item) => item.name.localeCompare(parish.name, 'es', { sensitivity: 'base' }) === 0,
    ).length > 1;
  if (!ambiguous) return parish.name;
  return `${parish.name} · ${territorialType(parish)} · ${parish.dpa_code ?? 'DPA no disponible'}`;
}
