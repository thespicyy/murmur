/* Remplit la page avec les donnees injectees par `lancer.py`.
 *
 * Volontairement sans bibliotheque : la maquette doit montrer ce que coute
 * reellement le portage, pas ce que coute un ecosysteme.
 */

const $ = (id) => document.getElementById(id);

function pont(action) {
  // Le pont vers Python. En version Tk, ces trois commandes demandaient de
  // reimplementer le deplacement, l'agrandissement et la zone utile de
  // l'ecran a la main.
  if (window.pywebview) window.pywebview.api[action]();
}

function basculerVolet() {
  document.body.classList.toggle("repliee");
}

function poser() {
  const d = DONNEES;

  $("vitesse").textContent = d.vitesse;
  $("rapport").textContent = d.rapport;
  $("corrections").textContent = d.corrections;
  $("termes").textContent = d.termes;
  $("remplacements").textContent = d.remplacements;
  $("mots").textContent = d.mots;
  $("dictees").textContent = d.dictees;
  $("gagne").textContent = d.gagne;
  $("nb-apps").textContent = d.nb_apps;
  $("serie").textContent = d.serie;
  $("pied-gauche").textContent = d.pied_gauche;
  $("pied-droite").textContent = d.pied_droite;

  if (d.tendance) {
    const t = $("tendance");
    t.textContent = d.tendance;
    if (d.hausse) t.classList.add("hausse");
  }

  // La jauge : l'arc fait 270 unites de long, on en decouvre une fraction.
  // L'animation part de zero a l'ouverture, la transition CSS fait le reste.
  requestAnimationFrame(() => {
    $("arc").style.strokeDashoffset = 270 * (1 - d.part_vitesse);
  });

  const usage = $("usage");
  d.applications.forEach((app, rang) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="picto">${app.picto}</div>
      <div class="piste">
        <div class="barre" style="width:${(app.part * 100).toFixed(0)}%;
             animation-delay:${rang * 60}ms">${(app.part * 100).toFixed(0)} %</div>
      </div>
      <div class="nom">${app.nom}<em>${app.mots}</em></div>`;
    usage.appendChild(li);
  });

  d.jours.forEach((nom) => {
    const div = document.createElement("div");
    div.textContent = nom;
    $("jours").appendChild(div);
  });

  d.mois.forEach((mois) => {
    const span = document.createElement("span");
    span.textContent = mois.nom;
    span.style.flex = mois.semaines;
    $("mois").appendChild(span);
  });

  // Cinq paliers, du plus pale au plus vif — comme la version Tk, mais les
  // teintes sont calculees par le navigateur a partir d'une seule couleur.
  d.cases.forEach((valeur) => {
    const div = document.createElement("div");
    div.className = "case";
    div.style.background = valeur === null
      ? "transparent"
      : `color-mix(in srgb, var(--texte) ${valeur * 100}%, var(--carte-survol))`;
    if (valeur !== null) div.title = `${valeur.toFixed(0)}`;
    $("cases").appendChild(div);
  });
}

poser();
