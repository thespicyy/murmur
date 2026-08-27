/* Tracés des pictogrammes, en SVG.
 *
 * Repris de `icones.TRACES`, qui les décrivait pour Pillow. Le navigateur les
 * lisse lui-même : plus de suréchantillonnage ×8, plus de cache d'images, plus
 * de PhotoImage à retenir pour que Tk ne les efface pas.
 *
 * Un seul jeu de coordonnées, sur un carré de 24, comme du côté Python — les
 * deux doivent rester interchangeables tant que la barre de dictée est en Tk.
 */

const TRACES = {
  dictees: '<rect x="9.5" y="3" width="5" height="10.5" rx="2.5"/>' +
    '<path d="M6.5 11a5.5 5.5 0 0 0 11 0"/>' +
    '<line x1="12" y1="16.5" x2="12" y2="20"/>' +
    '<line x1="8.5" y1="20" x2="15.5" y2="20"/>',

  dictionnaire: '<path d="M12 6.5v12.5M12 6.5 5 5v12.5L12 19M12 6.5 19 5v12.5L12 19"/>',

  /* Deux axes en équerre — ordonnées à gauche, abscisses en bas — et deux
   * barres évidées posées dessus. Les barres sont dessinées au trait, pas
   * remplies : c'est ce qui leur donne leur centre clair. */
  statistiques: '<path d="M4.3 4.5v15.2h15.4"/>' +
    '<rect x="7.6" y="10.4" width="5" height="6.6" rx="1.5"/>' +
    '<rect x="14.4" y="6.4" width="5" height="10.6" rx="1.5"/>',

  /* Roue dentée, comme la référence. Les trois curseurs qu'on avait avant
   * disaient « réglages » aussi bien, mais pas dans le même vocabulaire. */
  reglages: '<circle cx="12" cy="12" r="3"/>' +
    '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83' +
    'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 ' +
    '1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 ' +
    '0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51' +
    '-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82' +
    'l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 ' +
    '1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 ' +
    '1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 ' +
    '0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 ' +
    '0 0-1.51 1z"/>',

  app_navigateur: '<circle cx="12" cy="12" r="8"/>' +
    '<line x1="4" y1="12" x2="20" y2="12"/>' +
    '<ellipse cx="12" cy="12" rx="4" ry="8"/>',
  app_code: '<path d="M9 8 4.5 12 9 16M15 8l4.5 4L15 16"/>',
  app_terminal: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/>' +
    '<path d="M7 10l3 2.5L7 15M12.5 15.5h4.5"/>',
  app_message: '<path d="M5 17V7.5h14v8H9.5L5 19z"/>',
  app_courriel: '<rect x="3.5" y="6" width="17" height="12" rx="2"/>' +
    '<path d="M3.5 7.5 12 13.5 20.5 7.5"/>',
  app_document: '<path d="M6 20V4h9l3 3v13H6z"/><path d="M9 11h6M9 15h6"/>',
  app_note: '<rect x="5.5" y="5.5" width="13" height="13" rx="1"/>' +
    '<path d="M9 10h6M9 14h4"/>',
  app_media: '<circle cx="8" cy="17" r="3"/><circle cx="15" cy="15" r="3"/>' +
    '<path d="M11 17V5l7 2v8"/>',
  app_jeu: '<rect x="3" y="8" width="18" height="9" rx="4"/>' +
    '<path d="M7.5 10.5v4M5.5 12.5h4"/>' +
    '<circle cx="16" cy="11.5" r="1.3" fill="currentColor" stroke="none"/>' +
    '<circle cx="18.5" cy="14" r="1.3" fill="currentColor" stroke="none"/>',
  app_ia: '<path d="M12 3.5 13.6 9.4 19.5 11 13.6 12.6 12 18.5 10.4 12.6 ' +
    '4.5 11 10.4 9.4Z"/>',
  app_dossier: '<path d="M3.5 8v10.5h17V8M3.5 8V5.5h6l2 2.5h9"/>',
  app_autre: '<rect x="3.5" y="5" width="17" height="11" rx="2"/>' +
    '<path d="M9 20h6M12 16v4"/>',
};

function picto(nom, taille = 20) {
  const trace = TRACES[nom] || TRACES.app_autre;
  return `<svg width="${taille}" height="${taille}" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round">${trace}</svg>`;
}
