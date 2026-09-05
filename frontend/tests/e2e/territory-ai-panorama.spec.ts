import { expect, test } from '@playwright/test';
import { apiToken, e2eUsers } from './support/auth';

test('Territorio IA produce panorama y debate factual trazables para Gualaceo', async ({ request }) => {
  const token = process.env.E2E_TOKEN || await apiToken(request, process.env.E2E_USER_NAME || e2eUsers.manager);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json();
  const campaign = campaigns.items.find((item: { slug: string; name: string }) => item.slug === 'gualaceo-e2e-2027');
  expect(campaign).toBeTruthy();

  const panorama = await request.post(`/api/v1/campaigns/${campaign.id}/territory-ai/query`, {
    headers,
    data: { question: '¿Cuál es el panorama electoral de Gualaceo ahora?' },
  });
  expect(panorama.status()).toBe(200);
  const panoramaBody = await panorama.json();
  expect(panoramaBody.intent).toBe('ELECTORAL_PANORAMA');
  for (const value of ['34.784', '24.697', '71,00 %', '68,58 %', '71,89 %', '43.188']) {
    expect(panoramaBody.answer).toContain(value);
  }
  expect(panoramaBody.answer.toLowerCase()).toContain('no constituye una predicción electoral');
  expect([...new Set(panoramaBody.citations.map((item: { evidence_class: string }) => item.evidence_class))]).toEqual(expect.arrayContaining(['OFFICIAL', 'CAMPAIGN']));
  expect(panoramaBody.citations.some((item: { source_type: string }) => item.source_type === 'CITIZEN_NEED')).toBe(true);

  const participation = await request.post(`/api/v1/campaigns/${campaign.id}/territory-ai/query`, {
    headers,
    data: { question: '¿Cómo ha cambiado la participación electoral?' },
  });
  expect(participation.status()).toBe(200);
  const participationBody = await participation.json();
  expect(participationBody.intent).toBe('HISTORICAL_TURNOUT');
  expect(participationBody.model).toBe('territory-ai-fake-v2');
  expect(participationBody.answer).toContain('68,58 %');
  expect(participationBody.answer).toContain('71,89 %');
  expect(participationBody.answer).toContain('Proyección de participación V1');
  expect(participationBody.answer).toContain('24.697');
  expect(participationBody.answer).not.toContain('Respuesta grounded sintética');

  const debate = await request.post(`/api/v1/campaigns/${campaign.id}/territory-ai/query`, {
    headers,
    data: { question: 'Prepárame un resumen factual de la evidencia disponible sobre vialidad para un debate.' },
  });
  expect(debate.status()).toBe(200);
  const debateBody = await debate.json();
  expect(debateBody.intent).toBe('DEBATE_BRIEF');
  expect(debateBody.answer).toContain('Resumen factual para debate');
  expect(debateBody.answer).not.toMatch(/debe construir|prometemos|va a ganar/i);
});
