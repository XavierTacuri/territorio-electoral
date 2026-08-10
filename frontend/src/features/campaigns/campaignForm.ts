import { z } from 'zod';
import { isValidDateOnly, parseDateOnly } from '../../lib/dates';

const dateField = (required = false) =>
  z
    .string()
    .refine((value) => (!value && !required) || parseDateOnly(value) !== null, 'Usa DD/MM/AAAA.');

export const campaignFormSchema = z
  .object({
    name: z.string().trim().min(1, 'El nombre es obligatorio.'),
    slug: z
      .string()
      .trim()
      .min(1, 'El identificador es obligatorio.')
      .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Usa minúsculas, números y guiones.'),
    province_id: z.string().min(1, 'La provincia es obligatoria.'),
    canton_id: z.string().min(1, 'El cantón es obligatorio.'),
    office_type: z.enum(['MAYOR', 'URBAN_COUNCILOR', 'RURAL_COUNCILOR', 'PARISH_BOARD']),
    election_name: z.string().trim().min(1, 'El tipo de elección es obligatorio.'),
    election_date: dateField(true),
    start_date: dateField(),
    end_date: dateField(),
    status: z.enum(['DRAFT', 'ACTIVE', 'COMPLETED', 'ARCHIVED']),
    description: z.string(),
    is_active: z.boolean(),
  })
  .superRefine((values, context) => {
    const start = values.start_date ? parseDateOnly(values.start_date) : null;
    const end = values.end_date ? parseDateOnly(values.end_date) : null;
    const election = parseDateOnly(values.election_date);
    if (start && end && start > end)
      context.addIssue({
        code: 'custom',
        path: ['end_date'],
        message: 'La fecha final no puede ser anterior al inicio.',
      });
    if (start && election && election < start)
      context.addIssue({
        code: 'custom',
        path: ['election_date'],
        message: 'La elección no puede ser anterior al inicio.',
      });
  });

export type CampaignFormValues = z.infer<typeof campaignFormSchema>;

export function toCampaignPayload(values: CampaignFormValues, editing: boolean) {
  const common = {
    name: values.name.trim(),
    slug: values.slug.trim(),
    office_type: values.office_type,
    election_name: values.election_name.trim(),
    election_date: parseDateOnly(values.election_date),
    start_date: values.start_date ? parseDateOnly(values.start_date) : null,
    end_date: values.end_date ? parseDateOnly(values.end_date) : null,
    status: values.status,
    description: values.description.trim() || null,
    is_active: values.is_active,
  };
  if (!common.election_date || !isValidDateOnly(common.election_date))
    throw new Error('Fecha electoral inválida.');
  return editing ? common : { ...common, canton_id: Number(values.canton_id) };
}

export function slugify(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}
