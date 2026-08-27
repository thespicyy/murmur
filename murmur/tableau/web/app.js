/* Le tableau de bord.
 *
 * Aucune donnée n'est écrite ici : tout vient du pont Python
 * (`window.pywebview.api`), y compris les libellés — la page ne porte pas une
 * seule chaîne traduite, comme la version Tkinter les demandait au même
 * traducteur.
 *
 * Sans bibliothèque : le portage doit coûter ce qu'il coûte, pas ce que
 * coûterait un écosystème.
 */

const $ = (sel) => document.querySelector(sel);
const PAGES = ["dictees", "dictionnaire", "statistiques"];
/* Les réglages sont une page comme les autres, mais posée à part dans la
 * barre : c'est un ailleurs, pas une quatrième vue des mêmes données. */
const REGLAGES = "reglages";

let MOTS = {};
let PAGE = "statistiques";

const mot = (cle) => MOTS[cle] ?? cle;

/* -- ossature ------------------------------------------------------------ */

async function demarrer() {
  const [textes, etat] = await Promise.all([
    pywebview.api.textes(), pywebview.api.etat(),
  ]);
  MOTS = textes;
  if (etat.page) PAGE = etat.page;
  appliquerTheme(etat.theme);
  document.body.classList.toggle("repliee", etat.repliee);
  $("#pied-droite").textContent = mot("pied.maintien")
    .replace("{raccourci}", etat.raccourci);

  batirOnglets();
  brancherFenetre();
  await afficher(PAGE);

  // La fenêtre reste ouverte pendant qu'on dicte ailleurs : elle se tient au
  // courant plutôt que d'attendre qu'on la rouvre. Une requête d'une ligne
  // toutes les deux secondes coûte moins qu'un canal permanent entre les
  // deux processus.
  setInterval(rafraichir, 2000);
}

function appliquerTheme(theme) {
  // Le pont envoie le thème déjà résolu : « auto » a été traduit côté Python,
  // seul endroit qui sache lire le réglage de Windows.
  document.documentElement.dataset.theme =
    theme === "sombre" ? "sombre" : "clair";
}

function batirOnglets() {
  const nav = $("#onglets");
  nav.innerHTML = "";
  for (const cle of PAGES) {
    const div = document.createElement("div");
    div.className = "onglet" + (cle === PAGE ? " actif" : "");
    div.dataset.page = cle;
    div.innerHTML = `${picto(cle)}<span>${mot("page." + cle)}</span>`;
    div.onclick = () => afficher(cle);
    nav.appendChild(div);
  }
  const lien = document.createElement("div");
  lien.className = "onglet lien" + (PAGE === REGLAGES ? " actif" : "");
  lien.dataset.page = REGLAGES;
  lien.innerHTML = `${picto("reglages")}<span>${mot("reglages")}</span>`;
  lien.onclick = () => afficher(REGLAGES);
  nav.appendChild(lien);
}

function brancherFenetre() {
  for (const bouton of document.querySelectorAll("[data-fenetre]")) {
    bouton.onclick = () => pywebview.api[bouton.dataset.fenetre]();
  }

  // Le déplacement ne peut pas être mené ici : les événements de souris
  // cessent d'arriver dès que le curseur sort de la fenêtre, et un glisser
  // sort forcément — c'est même son but quand on vise un bord de l'écran.
  // Python suit le curseur à notre place.
  $(".titre").addEventListener("mousedown", (e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    pywebview.api.deplacer();
  });
  $(".titre").addEventListener("dblclick", (e) => {
    if (!e.target.closest("button")) pywebview.api.agrandir();
  });

  // Le bord haut appartient à la page depuis qu'on lui a rendu les pixels du
  // cadre : Windows n'y voit plus de poignée, la page la redemande.
  $("#poignee-haut").addEventListener("mousedown", (e) => {
    if (e.button === 0) pywebview.api.redimensionner_haut();
  });
  $("#volet").onclick = () => {
    const repliee = document.body.classList.toggle("repliee");
    pywebview.api.replier(repliee);
  };
}

async function afficher(page) {
  PAGE = page;
  for (const onglet of document.querySelectorAll(".onglet")) {
    onglet.classList.toggle("actif", onglet.dataset.page === page);
  }
  for (const lien of document.querySelectorAll(".lien")) {
    lien.classList.toggle("actif", page === REGLAGES);
  }
  if (page === "statistiques") await pageInsights();
  else if (page === "dictees") await pageDictees();
  else if (page === REGLAGES) await pageReglages();
  else await pageDictionnaire();
}

async function rafraichir() {
  // Le dictionnaire n'est jamais rafraichi seul : une saisie en cours serait
  // effacee sous les doigts.
  if (PAGE === "statistiques") await pageInsights({ discret: true });
  else if (PAGE === "dictees" && !recherche) await pageDictees();
}

/* -- page Insights ------------------------------------------------------- */

//: Décalage du calendrier, en pages de 22 semaines. 0 = jusqu'à aujourd'hui.
let decalage = 0;

async function pageInsights({ discret = false } = {}) {
  const d = await pywebview.api.insights();
  $("#pied-gauche").textContent = d.pied.gauche;

  // Redessiner l'entête à chaque rafraîchissement ferait clignoter la page :
  // on ne bâtit qu'une fois, puis on réécrit les valeurs.
  if (!discret || !$("#carte-vitesse")) {
    $("#panneau").innerHTML = gabaritInsights();
    brancherCalendrier();
  }
  remplirInsights(d, discret);
}

/* L'organisation reprend celle de la référence : une seule grille de quatre
 * colonnes pour les deux rangées, ce qui aligne les bords verticaux. En haut,
 * deux cartes étroites et une large ; en bas, deux cartes à parts égales. */
function gabaritInsights() {
  return `
    <div class="entete">
      <h1>${mot("page.statistiques")}</h1>
      <p>${mot("stats.sous_titre")}</p>
    </div>
    <section class="grille">
      <article class="carte" id="carte-vitesse">
        <div class="chiffre" id="vitesse">—</div>
        <div class="legende">${mot("stats.vitesse")}</div>
        ${gabaritJauge()}
      </article>

      <article class="carte">
        <div class="chiffre" id="corrections">—</div>
        <div class="legende">${mot("stats.corrections")}</div>
        <div class="filet"></div>
        <div class="detail"><b id="termes">—</b>${mot("stats.termes")}</div>
        <div class="detail"><b id="remplacements">—</b>${mot("stats.remplacements")}</div>
      </article>

      <article class="carte double">
        <span class="tendance" id="tendance"></span>
        <div class="chiffre" id="mots">—</div>
        <div class="legende">${mot("stats.mots")}</div>
        <div class="filet"></div>
        <div class="colonnes">
          <div class="detail" id="dictees"></div>
          <div class="detail" id="gagne"></div>
        </div>
      </article>

      <article class="carte double">
        <div class="entete-carte">
          <h2>${mot("stats.applications")}</h2>
          <span class="appoint">${mot("stats.applications.total")}
            <b id="nb-apps"></b></span>
        </div>
        <ul class="usage" id="usage"></ul>
      </article>

      <article class="carte double">
        <div class="entete-carte">
          <h2 id="serie">—</h2>
          <span class="appoint">${mot("stats.record")}
            <b id="record"></b></span>
        </div>
        <div class="mois">
          <button class="fleche" id="avant" title="◀">${chevron(-1)}</button>
          <div class="etiquettes" id="etiquettes-mois"></div>
          <button class="fleche" id="apres" title="▶">${chevron(1)}</button>
        </div>
        <div class="calendrier">
          <div class="jours" id="jours"></div>
          <div class="grille-jours" id="cases"></div>
        </div>
      </article>
    </section>
    <div class="infobulle" id="infobulle"></div>`;
}

//: Longueur de l'arc de la jauge, en unites du viewBox. Un demi-cercle de
//: rayon 80 : pi x 80, arrondi.
const JAUGE = 252;

/* Deux arcs et rien d'autre : le rail, et la portion parcourue. Les anneaux
 * de halo empruntes au graphe en entonnoir ont ete retires — sur une carte
 * claire, ils ne se lisaient pas comme une profondeur mais comme une ombre
 * sale autour de la jauge. */
function gabaritJauge() {
  return `
    <figure class="jauge">
      <svg viewBox="0 0 192 108">
                <path class="arc rail" d="M16 96a80 80 0 0 1 160 0" stroke-width="18"/>
        <path class="arc actif" id="arc" d="M16 96a80 80 0 0 1 160 0"
              stroke-width="18" stroke-dasharray="252" stroke-dashoffset="252"/>
      </svg>
      <figcaption>
        <div class="rapport" id="rapport">—</div>
        <div class="sous">${mot("stats.clavier")}</div>
      </figcaption>
    </figure>`;
}

function chevron(sens) {
  const d = sens < 0 ? "M15 5 8 12l7 7" : "M9 5l7 7-7 7";
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2" stroke-linecap="round"
    stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function remplirInsights(d, discret) {
  $("#vitesse").textContent = d.vitesse.valeur;
  $("#rapport").textContent = d.vitesse.rapport ? "×" + d.vitesse.rapport : "—";
  $("#corrections").textContent = d.corrections.total;
  $("#termes").textContent = d.corrections.termes;
  $("#remplacements").textContent = d.corrections.remplacements;
  $("#mots").textContent = d.volume.mots;
  $("#dictees").textContent = d.volume.dictees;
  $("#gagne").textContent = d.volume.gagne;
  $("#nb-apps").textContent = d.applications.total;
  $("#serie").textContent = d.activite.serie;
  $("#record").textContent = d.activite.record;

  const t = $("#tendance");
  t.textContent = d.volume.tendance
    ? (d.volume.tendance.hausse ? "↗ " : "↘ ") + d.volume.tendance.texte : "";
  t.classList.toggle("hausse", !!d.volume.tendance?.hausse);

  // L'animation ne joue qu'à l'ouverture : la rejouer toutes les deux
  // secondes ferait osciller l'aiguille sans raison.
  const arc = $("#arc");
  if (discret) arc.style.transition = "none";
  requestAnimationFrame(() => {
    arc.style.strokeDashoffset = JAUGE * (1 - d.vitesse.part);
    if (discret) requestAnimationFrame(() => (arc.style.transition = ""));
  });

  if (!discret) {
    remplirUsage(d.applications.lignes);
    remplirCalendrier(d.activite);
  }
}

//: Part de la ligne occupée par une barre à 100 %. Le reste revient au nom,
//: qui doit rester lisible même derrière la plus longue des barres.
const PISTE = 56;

function remplirUsage(lignes) {
  const liste = $("#usage");
  liste.innerHTML = "";
  lignes.forEach((app, rang) => {
    const li = document.createElement("li");
    // La barre est mesurée sur PISTE % de la ligne, et le nom la suit
    // immédiatement : posé à une abscisse fixe, il flottait loin de la barre
    // qu'il légende, et d'autant plus loin qu'elle était courte.
    li.innerHTML = `
      <div class="picto">${picto(app.picto)}</div>
      <div class="barre" style="width:${(app.part * PISTE).toFixed(1)}%;
           animation-delay:${rang * 60}ms">${app.pourcentage}</div>
      <div class="nom">${app.nom}<em>${app.mots}</em></div>`;
    liste.appendChild(li);
  });
}

/* -- calendrier d'activité ------------------------------------------------
 *
 * Cinq paliers plutôt qu'un dégradé continu : l'œil compare mal deux teintes
 * voisines mais distingue sans effort quatre marches — c'est ce que fait la
 * référence, et c'est ce que le composant heatmap dont on s'inspire appelle
 * ses « niveaux ». Le palier est calculé côté Python : c'est une règle de
 * l'application, pas un choix d'affichage.
 */

function brancherCalendrier() {
  $("#avant").onclick = () => glisserCalendrier(1);
  $("#apres").onclick = () => glisserCalendrier(-1);
}

async function glisserCalendrier(pas) {
  const vise = Math.max(0, decalage + pas);
  if (vise === decalage) return;
  decalage = vise;
  remplirCalendrier(await pywebview.api.calendrier(decalage));
}

function remplirCalendrier(activite) {
  $("#etiquettes-mois").innerHTML = activite.mois
    .map((m) => `<span style="flex:${m.semaines}">${m.nom}</span>`).join("");
  $("#jours").innerHTML = activite.jours
    .map((nom) => `<div>${nom}</div>`).join("");
  // Le bouton de droite est éteint sur la page la plus récente : rien à
  // montrer au-delà d'aujourd'hui.
  $("#apres").disabled = decalage === 0;

  const cases = $("#cases");
  cases.innerHTML = "";
  activite.cases.forEach((jour, rang) => {
    const div = document.createElement("div");
    div.className = "case";
    if (jour === null) {
      // Les cases de remplissage restent vides : les peindre au palier le
      // plus pâle inventerait des jours.
      div.classList.add("creuse");
    } else {
      div.dataset.niveau = jour.niveau;
      div.dataset.titre = jour.titre;
      // Entrée décalée, comme le composant dont on s'inspire : la grille se
      // remplit en une vague plutôt que d'apparaître d'un bloc.
      div.style.animationDelay = `${Math.min(600, rang * 3)}ms`;
    }
    cases.appendChild(div);
  });
  brancherInfobulle(cases);
}

function brancherInfobulle(grille) {
  const bulle = $("#infobulle");
  grille.onmouseover = (e) => {
    const case_ = e.target.closest(".case[data-titre]");
    if (!case_) return;
    bulle.textContent = case_.dataset.titre;
    bulle.classList.add("visible");
    const r = case_.getBoundingClientRect();
    // Posée au-dessus de la case et centrée dessus, puis ramenée dans la
    // fenêtre : contre le bord droit, elle sortirait de l'écran.
    const x = Math.min(window.innerWidth - bulle.offsetWidth - 8,
                       Math.max(8, r.left + r.width / 2 - bulle.offsetWidth / 2));
    bulle.style.transform = `translate(${x}px, ${r.top - bulle.offsetHeight - 8}px)`;
  };
  grille.onmouseleave = () => bulle.classList.remove("visible");
}

window.addEventListener("pywebviewready", demarrer);

/* -- page Dictation ------------------------------------------------------ */

let recherche = "";
let limite = 40;
let minuteur = null;

async function pageDictees({ discret = false } = {}) {
  const d = await pywebview.api.dictees(limite, recherche);
  $("#pied-gauche").textContent = d.pied.gauche;

  // L'en-tête et le champ ne sont bâtis qu'une fois : les refaire à chaque
  // frappe rendrait le focus et le texte saisi.
  if (!$("#recherche")) {
    $("#panneau").innerHTML = `
      <div class="entete">
        <h1>${mot("page.dictees")}</h1><p id="sous-titre"></p>
      </div>
      <input class="recherche" id="recherche" type="text"
             placeholder="${mot("dictees.recherche")}">
      <div id="liste"></div>`;
    const champ = $("#recherche");
    champ.value = recherche;
    champ.addEventListener("input", () => {
      // On attend une pause dans la frappe : sans ce délai, taper « portfolio »
      // déclencherait neuf requêtes et neuf reconstructions de liste.
      clearTimeout(minuteur);
      minuteur = setTimeout(() => {
        recherche = champ.value;
        limite = 40;
        pageDictees();
      }, 220);
    });
  }
  $("#sous-titre").textContent = d.sous_titre;
  remplirDictees(d);
}

function remplirDictees(d) {
  const liste = $("#liste");
  if (!d.groupes.length) {
    liste.innerHTML = `<div class="vide">${recherche
      ? mot("dictees.sans_resultat")
      : mot("dictees.vide") + "\n" + mot("dictees.vide.aide")
          .replace("{raccourci}", $("#pied-droite").textContent
            .replace(/^\S+\s/, ""))}</div>`;
    return;
  }

  liste.innerHTML = d.groupes.map((groupe) => `
    <div class="jour">${groupe.titre}</div>
    <div class="groupe">${groupe.lignes.map((ligne) => `
      <div class="dictee" data-id="${ligne.id}">
        <div class="heure">${ligne.heure}</div>
        <div class="texte">${echapper(ligne.texte)}</div>
        <div class="actions">
          <button class="action" data-copier title="${mot("dictees.copier")}">
            ${pictoAction("copier")}</button>
          <button class="action danger" data-supprimer
                  title="${mot("dictees.supprimer")}">
            ${pictoAction("supprimer")}</button>
        </div>
      </div>`).join("")}</div>`).join("")
    + (d.reste ? `<button class="plus">${mot("dictees.plus")}</button>` : "");

  for (const bouton of liste.querySelectorAll("[data-copier]")) {
    bouton.onclick = (e) => copier(e.target.closest(".dictee"));
  }
  for (const bouton of liste.querySelectorAll("[data-supprimer]")) {
    bouton.onclick = (e) => supprimer(e.target.closest(".dictee"));
  }
  const plus = liste.querySelector(".plus");
  if (plus) plus.onclick = () => { limite += 40; pageDictees(); };
}

async function copier(ligne) {
  await navigator.clipboard.writeText(ligne.querySelector(".texte").textContent);
}

async function supprimer(ligne) {
  await pywebview.api.supprimer_dictee(Number(ligne.dataset.id));
  // Retirée sur place plutôt que par une reconstruction : la liste ne
  // sursaute pas, et le défilement reste où il était.
  ligne.style.height = ligne.offsetHeight + "px";
  requestAnimationFrame(() => {
    ligne.style.cssText += ";height:0;opacity:0;margin:0;padding:0" +
      ";overflow:hidden;transition:all 160ms ease";
    setTimeout(() => ligne.remove(), 180);
  });
}

/* -- page Dictionary ----------------------------------------------------- */

async function pageDictionnaire() {
  const d = await pywebview.api.dictionnaire();
  $("#panneau").innerHTML = `
    <div class="entete">
      <h1>${mot("page.dictionnaire")}</h1><p>${d.sous_titre}</p>
    </div>
    <div class="ajout">
      <label><span>${mot("dico.terme")}</span>
        <input id="terme" type="text"></label>
      <label><span>${mot("dico.variante")}</span>
        <input id="variante" type="text"></label>
      <button class="principal" id="ajouter">${mot("dico.ajouter")}</button>
    </div>
    <div id="termes"></div>`;

  $("#ajouter").onclick = ajouterTerme;
  for (const champ of ["terme", "variante"]) {
    $("#" + champ).addEventListener("keydown", (e) => {
      if (e.key === "Enter") ajouterTerme();
    });
  }
  remplirTermes(d.termes);
}

function remplirTermes(termes) {
  const liste = $("#termes");
  if (!termes.length) {
    liste.innerHTML = `<div class="vide">${mot("dico.vide")}\n\n${
      mot("dico.vide.aide").replace("{raccourci}", "")}</div>`;
    return;
  }
  liste.innerHTML = termes.map((t) => `
    <div class="terme" data-terme="${echapper(t.terme)}">
      <div class="texte">
        <div><span class="nom">${echapper(t.terme)}</span>${
          t.hors_prompt ? `<span class="meta">${mot("dico.hors_prompt")}</span>` : ""}${
          t.usages ? `<span class="meta">${t.usages}</span>` : ""}</div>
        ${t.variantes.length ? `<div class="variantes"><span class="etiquette">${
          mot("dico.corrige")}</span>${t.variantes.map(
          (v) => `<span class="variante">${echapper(v)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="actions">
        <button class="action danger" title="${mot("dico.retirer")}">
          ${pictoAction("supprimer")}</button>
      </div>
    </div>`).join("");

  for (const bouton of liste.querySelectorAll(".action")) {
    bouton.onclick = async (e) => {
      const carte = e.target.closest(".terme");
      await pywebview.api.retirer_terme(carte.dataset.terme);
      pageDictionnaire();
    };
  }
}

async function ajouterTerme() {
  const terme = $("#terme").value.trim();
  if (!terme) return;
  const reponse = await pywebview.api.ajouter_terme(terme,
                                                    $("#variante").value);
  if (!reponse.ok) {
    $("#terme").focus();
    return;
  }
  await pageDictionnaire();
  $("#terme").focus();
}

/* -- page Settings ------------------------------------------------------- */
/*
 * Le formulaire n'est pas écrit ici : sa structure — quels réglages existent,
 * de quel type, dans quelle section — vient de Python (`donnees.CHAMPS`). Ce
 * sont des règles de l'application, pas des choix de mise en page, et elles se
 * vérifient sans ouvrir de fenêtre.
 */

async function pageReglages() {
  const d = await pywebview.api.reglages();
  $("#panneau").innerHTML = `
    <div class="entete">
      <h1>${mot("reglages")}</h1><p>${mot("reg.sous_titre")}</p>
    </div>
    ${d.sections.map(gabaritSection).join("")}
    <div class="barre-enregistrer">
      <span class="message" id="message"></span>
      <button class="principal" id="enregistrer">${d.enregistrer}</button>
    </div>`;

  $("#enregistrer").onclick = enregistrerReglages;
  for (const segment of document.querySelectorAll(".segment")) {
    segment.onclick = () => {
      for (const frere of segment.parentElement.children) {
        frere.classList.toggle("actif", frere === segment);
      }
    };
  }
}

function gabaritSection(section) {
  return `
    <div class="titre-section">${section.titre}</div>
    <article class="carte reglages">
      ${section.champs.map(gabaritChamp).join("")}
    </article>
    ${section.note ? `<p class="note">${echapper(section.note)}</p>` : ""}`;
}

function gabaritChamp(champ) {
  return `
    <div class="reglage">
      <div class="intitule">
        <span>${champ.libelle}</span>
        ${champ.aide ? `<em>${champ.aide}</em>` : ""}
      </div>
      ${commande(champ)}
    </div>`;
}

function commande(champ) {
  if (champ.type === "texte") {
    return `<input type="text" data-chemin="${champ.chemin}"
                   value="${echapper(String(champ.valeur))}">`;
  }
  if (champ.type === "liste") {
    // Une vraie liste déroulante, pas des pastilles : les micros d'une
    // machine se comptent par dizaines et portent des noms longs.
    return `<select data-chemin="${champ.chemin}">
        ${champ.choix.map((c) => `<option value="${echapper(String(c.valeur))}"
          ${c.valeur === champ.valeur ? "selected" : ""}
          >${echapper(c.libelle)}</option>`).join("")}
      </select>`;
  }
  if (champ.type === "case") {
    // Un interrupteur plutôt qu'une case : la case de Windows est dessinée par
    // le système et ignore la palette — c'est ce qui rendait les réglages
    // illisibles en thème sombre du côté Tkinter.
    return `<label class="bascule">
        <input type="checkbox" data-chemin="${champ.chemin}"
               ${champ.valeur ? "checked" : ""}><span></span></label>`;
  }
  return `<div class="segments" data-chemin="${champ.chemin}">
      ${champ.choix.map((c) => `<div class="segment${
        c.valeur === champ.valeur ? " actif" : ""}"
        data-valeur="${c.valeur}">${c.libelle}</div>`).join("")}
    </div>`;
}

function valeursSaisies() {
  const valeurs = {};
  for (const champ of document.querySelectorAll("[data-chemin]")) {
    if (champ.classList.contains("segments")) {
      valeurs[champ.dataset.chemin] =
        champ.querySelector(".actif")?.dataset.valeur;
    } else if (champ.type === "checkbox") {
      valeurs[champ.dataset.chemin] = champ.checked;
    } else if (champ.tagName === "SELECT") {
      valeurs[champ.dataset.chemin] = champ.value;
    } else {
      valeurs[champ.dataset.chemin] = champ.value.trim();
    }
  }
  return valeurs;
}

async function enregistrerReglages() {
  const message = $("#message");
  const reponse = await pywebview.api.enregistrer_reglages(valeursSaisies());

  // Le succès ne s'annonce pas par une alerte à fermer : c'est une corvée à
  // chaque réglage. Seul l'échec doit arrêter — sans quoi l'utilisateur
  // croirait son nouveau raccourci en service.
  message.className = "message " + (reponse.ok ? "ok" : "erreur");
  message.textContent = reponse.ok
    ? (reponse.avertissement || mot("reg.enregistre"))
    : `${reponse.titre} — ${reponse.erreur}`;
  if (!reponse.ok) return;

  // La langue et le thème ont pu changer : toute la page en dépend, jusqu'aux
  // onglets. On redemande l'état plutôt que de deviner ce qui a bougé.
  const [textes, etat] = await Promise.all([
    pywebview.api.textes(), pywebview.api.etat(),
  ]);
  MOTS = textes;
  appliquerTheme(etat.theme);
  batirOnglets();
  const garde = message.textContent;
  await pageReglages();
  $("#message").className = "message ok";
  $("#message").textContent = garde;
}

/* -- outils -------------------------------------------------------------- */

function echapper(texte) {
  const div = document.createElement("div");
  div.textContent = texte;
  return div.innerHTML;
}

function pictoAction(nom) {
  const traces = {
    copier: '<rect x="9" y="9" width="11" height="11" rx="2"/>' +
      '<path d="M5 15V5h10"/>',
    supprimer: '<path d="M5 7h14M10 7V5h4v2M8 7l1 12h6l1-12"/>',
  };
  return `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
    stroke-linejoin="round">${traces[nom]}</svg>`;
}
