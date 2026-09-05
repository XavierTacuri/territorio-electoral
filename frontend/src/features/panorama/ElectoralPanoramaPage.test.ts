import { describe, expect, it } from 'vitest';
import { panoramaQuestions } from './ElectoralPanoramaPage';

describe('Panorama Electoral', () => {
  it('ofrece preguntas descriptivas sin predicción ni persuasión', () => {
    expect(panoramaQuestions).toContain('¿Cuál es el panorama electoral actual?');
    expect(panoramaQuestions).toContain('¿Qué necesidades se han registrado por parroquia?');
    expect(panoramaQuestions.join(' ')).not.toMatch(/ganando|persuadir|atacar|convencer/i);
  });
});
