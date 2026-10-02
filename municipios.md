# Municipios — estado en OpoTrack

Checklist de ayuntamientos con conector propio. Bajo cada uno tienes: **estado en la app**, **qué falta**, **problema** (si lo hay) y una línea **Sugerencias** para que apuntes cómo seguir con él.

**Leyenda:** ✅ hecho y activo · ⏳ viable, falta una muestra de su HTML · ❌ no raspable sin navegador → se cubre por el **BOP de su provincia** (que OpoTrack ya rastrea).

**Para añadir uno nuevo:** guarda su página de empleo como «Página web, solo HTML» en `fixtures/`, escribe el conector en `opotrack/fuentes/` (parser + test) y regístralo en `opotrack/fuentes/__init__.py` y en `opotrack/seed.py`; así queda activo en la sección *Ayuntamientos* del buscador.

---

## Resumen

- [x] Loja (GR) — `AYTLOJA`
- [x] Benalmádena (MA) — `AYTBEN`
- [x] Huétor Tájar (GR) — `AYTHT`
- [x] Antequera (MA) — `AYTANT`
- [x] Málaga capital (MA) — `AYTMLG`
- [x] Motril (GR) — `AYTMOT`
- [x] Córdoba capital (CO) — `AYTCOR`
- [ ] Marbella (MA) — falta HTML
- [ ] Maracena (GR) — falta HTML
- [x] Nerja (MA) — `AYTNER`
- [ ] Santa Fe (GR) — falta HTML (por confirmar)
- [ ] Fuengirola (MA) — ❌ sede JS → BOP Málaga
- [ ] Atarfe (GR) — ❌ página sin convocatorias → BOP Granada
- [ ] Montefrío (GR) — ❌ web sin convocatorias → BOP Granada
- [ ] Salar (GR) — ❌ sede JS → BOP Granada
- [ ] Granada capital (GR) — ❌ web con frames → BOP Granada
- [ ] Torremolinos (MA) — ❌ portal JS → BOP Málaga
- [ ] Mijas (MA) — ❌ sede JS → BOP Málaga
- [ ] Jaén capital (J) — ❌ sede JS → BOP Jaén

---

## ✅ Implementados (activos en la app)

### Loja (Granada) — `AYTLOJA`
- **Estado en la app:** activo. Sección *Ayuntamientos*, ámbito «Loja».
- **Fuente:** http://www.aytoloja.org/empleo/empleopublico.htm (HTML estático).
- **Cómo funciona:** un anuncio por cada PDF del contenido; referencia = hash del nombre del archivo.
- **Problema:** ninguno.
- **Sugerencias:** _(añade aquí)_

### Benalmádena (Málaga) — `AYTBEN`
- **Estado en la app:** activo. Ámbito «Benalmádena».
- **Fuente:** https://www.benalmadena.es/contenido.php?m=benalmadena-delegaciones&s=convocatorias-de-personal
- **Cómo funciona:** una fila por convocatoria (código `C<NNN>`), con fecha «Actualizado» y título.
- **Problema:** ninguno.
- **Sugerencias:** _(añade aquí)_

### Huétor Tájar (Granada) — `AYTHT`
- **Estado en la app:** activo. Ámbito «Huétor Tájar».
- **Fuente:** https://huetortajar.org/ayuntamiento/convocatorias-de-empleo-publico/ (WordPress).
- **Cómo funciona:** un anuncio por encabezado de convocatoria; enlace a las bases; se ignoran separadores. La página guarda todo el histórico (~79 en la primera búsqueda; luego solo lo nuevo).
- **Problema:** ninguno. (Nota: mucho histórico; la primera búsqueda marca muchas como nuevas.)
- **Sugerencias:** _(añade aquí)_

### Antequera (Málaga) — `AYTANT`
- **Estado en la app:** activo. Ámbito «Antequera». Lee Oposiciones + Concursos + Bolsas.
- **Fuente:** https://www.antequera.es/ayuntamiento/tablon-de-anuncios/Empleo-Publico/oposiciones/
- **Cómo funciona:** un anuncio por convocatoria (con su fecha de publicación). En la web real, 7 oposiciones.
- **Problema (resuelto):** los enlaces en vivo eran relativos y daban 404 (iban a localhost); ahora se resuelven a absolutos y hay una reparación automática al arrancar para las ya guardadas.
- **Sugerencias:** _(añade aquí)_

### Málaga capital (Málaga) — `AYTMLG`
- **Estado en la app:** activo. Ámbito «Málaga».
- **Fuente:** https://www.malaga.eu/el-ayuntamiento/ofertas-de-empleo-publico/ayuntamiento-de-malaga/
- **Cómo funciona:** un anuncio por convocatoria (título + especialidad), enlace a su ficha `?id=…`. **Omite las cerradas** (las que en «Trámite» ponen «Cerrado…»): en real, 43 abiertas de 70.
- **Problema:** ninguno. Solo se ven las administrativas/informáticas en la bandeja (el resto —oficios, policía…— quedan en «sin coincidencia»).
- **Sugerencias:** _(añade aquí)_

### Motril (Granada) — `AYTMOT`
- **Estado en la app:** activo. Ámbito «Motril».
- **Fuente:** https://motril.es/recursos-humanos/oferta-empleo-publico/ofertas-empleo/ (WordPress).
- **Cómo funciona:** un anuncio por expediente (`/oferta-empleo/expediente-…`), agrupados por año/tipo. En real, 28 items.
- **Problema:** el listado no trae fecha por convocatoria (queda sin fecha en la ficha).
- **Sugerencias:** _(añade aquí)_

### Córdoba capital (Córdoba) — `AYTCOR`
- **Estado en la app:** activo. Ámbito «Córdoba». Al ser «resto de Andalucía», solo casa la rama de **informática**.
- **Fuente:** https://www.cordoba.es/sede/tramites/empleo/convocatorias (Drupal).
- **Cómo funciona:** un anuncio por convocatoria **abierta** (acordeón), con su código `[RHU..-AAAA-NN]` y fecha de inicio de plazo.
- **Cómo se muestra:** refleja el estado «Convocatorias Abiertas»; si no hay ninguna abierta, aparece como «0/0» (no como «no hay publicación»).
- **Problema:** solo salen las **abiertas** (las que hay en cada momento); el histórico completo vive en un portal aparte (`empleo.eprinsa.es`) que es JavaScript y no se puede raspar. El enlace de cada ficha apunta a la página general de convocatorias (no hay URL propia por convocatoria).
- **Sugerencias:** _(añade aquí)_

### Nerja (Málaga) — `AYTNER`
- **Estado en la app:** activo. Ámbito «Nerja».
- **Fuente:** https://sedeelectronica.nerja.es/portal/tablonVirtual.do?subseccion=DEP.EMP&opc_id=175&pes_cod=5&ent_id=1&idioma=1 (tablón de la sede electrónica).
- **Cómo funciona:** un anuncio por expediente (`expId`) del tablón de empleo; excluye las sesiones de junta de gobierno. En real, 169 items (histórico del tablón, como Huétor Tájar); en la bandeja solo destacan los administrativos/informáticos.
- **Problema:** las fechas del tablón son de **exposición** (no el plazo del proceso), por eso no se filtran. Posible riesgo: el servlet podría exigir sesión; el conector la establece antes de pedir el listado. Si en real diera 0, revisar sesión/cookies.
- **Sugerencias:** _(añade aquí)_

---

## ⏳ Viables — falta una muestra del HTML

Basta guardar la página como «Página web, solo HTML» para usarla de fixture.

### Marbella (Málaga)
- **Estado en la app:** sin conector todavía.
- **Fuente:** https://ayuntamiento.marbella.es/oferta-publica/empleo-publico.html (CMS servido, «Procesos en curso»).
- **Qué falta:** una muestra del HTML.
- **Problema:** ninguno previsto (es servida). Las solicitudes van por su sede JS, pero el **listado** sí se sirve.
- **Sugerencias:** _(añade aquí)_

### Maracena (Granada)
- **Estado en la app:** sin conector todavía.
- **Fuente:** https://maracena.es/empleo-publico/ (WordPress; acordeones con PDFs etiquetados BASES-BOP/SOLICITUD/LISTAS…).
- **Qué falta:** una muestra del HTML, guardada como «solo HTML» (un único archivo, sin la carpeta de recursos `_files`).
- **Problema:** ninguno previsto (es servida).
- **Sugerencias:** _(añade aquí)_

### Santa Fe (Granada) — por confirmar
- **Estado en la app:** sin conector todavía.
- **Fuente:** https://www.santafe.es/ (CMS PHP con URLs de sesión, `PHPSESSID`).
- **Qué falta:** una muestra del HTML de su sección de empleo/oposiciones para confirmar que es raspable.
- **Problema posible:** las URLs con sesión pueden ser inestables; se confirmará al ver el HTML.
- **Sugerencias:** _(añade aquí)_

---

## ❌ No raspables sin navegador → cubiertos por su BOP

Estos ya te llegan por el conector del **BOP** de su provincia (Granada/Málaga/Jaén), que OpoTrack rastrea. No hace falta nada para seguir cubriéndolos; se listan por si su web cambia en el futuro.

### Fuengirola (Málaga) — → BOP Málaga
- **Problema:** la sede (`sede.fuengirola.es`, plataforma T-Systems STA) carga el empleo por JavaScript (fetch normal = tabla vacía). El portal `fuengirola.portalemp.com` son ofertas **privadas/temporales**, no oposiciones.
- **Qué haría falta:** navegador headless (fuera de alcance) o que cambien de web.
- **Sugerencias:** _(añade aquí)_

### Atarfe (Granada) — → BOP Granada
- **Problema:** la página `atarfe.es/bolsa-de-empleo` es informativa y antigua (contenido de 2017-2018), sin convocatorias ni PDFs. Sus oposiciones salen por BOP Granada/BOE.
- **Qué haría falta:** otra página suya que sí liste convocatorias actuales (si existe).
- **Sugerencias:** _(añade aquí)_

### Montefrío (Granada) — → BOP Granada
- **Problema:** su categoría de empleo (`montefrio.es/category/empleo/`) solo tiene 2 entradas del programa «EMPLEA-T», sin convocatorias de oposiciones.
- **Qué haría falta:** una página suya con las bases (si existe).
- **Sugerencias:** _(añade aquí)_

### Salar (Granada) — → BOP Granada
- **Problema:** su sede (`salar.sedelectronica.es`) es JavaScript y es un municipio pequeño sin sección web estable de empleo.
- **Sugerencias:** _(añade aquí)_

### Granada capital (Granada) — → BOP Granada
- **Problema:** `granada.org` es un sitio antiguo (Lotus Domino) con marcos/frames; el fetch devuelve vacío. Su sede alternativa (`sede.granada.org`) es JavaScript.
- **Qué haría falta:** localizar una vista servida sin frames (si existe) o navegador headless.
- **Sugerencias:** _(añade aquí)_

### Torremolinos (Málaga) — → BOP Málaga
- **Problema:** `transparencia.torremolinos.es` es un portal JavaScript; el fetch devuelve vacío.
- **Sugerencias:** _(añade aquí)_

### Mijas (Málaga) — → BOP Málaga
- **Problema:** su sede (`sede.mijas.es`, `se_contenedor1.jsp`) es JavaScript.
- **Sugerencias:** _(añade aquí)_

### Jaén capital (Jaén) — → BOP Jaén
- **Problema:** su sede (`sede.aytojaen.es`, plataforma STA) es JavaScript.
- **Sugerencias:** _(añade aquí)_

---

## Resto de municipios → ya cubiertos por BOP

No necesitan conector propio: sus convocatorias se publican (por ley) en el BOP de su provincia, y OpoTrack ya rastrea esos boletines. Regla de los perfiles por defecto: **Granada y Málaga → administrativa + informática; resto → solo informática.**

- **BOP Granada** (cubre, entre otros): Villanueva de Mesía, Íllora, Alhama de Granada, Pinos Puente, Armilla, Las Gabias, Guadix, Almuñécar, Baza…
- **BOP Málaga:** Archidona, Villanueva del Trabuco, Cártama, Alhaurín de la Torre, Rincón de la Victoria, Coín, Vélez-Málaga, Ronda, Estepona…
- **BOP Jaén:** Andújar, Linares, Úbeda, Baeza…
- **BOP Córdoba:** Lucena, Puente Genil, Cabra…
- **BOP Sevilla:** Écija… · **BOP Almería:** El Ejido, Almería, Roquetas…

### Boletines provinciales (fuente fiable)
| Provincia | BOP | En OpoTrack |
|-----------|-----|-------------|
| Granada | https://bop.dipgra.es | ✅ `BOPG` |
| Málaga | https://www.bopmalaga.es | ✅ `BOPMA` |
| Jaén | https://bop.dipujaen.es | ✅ `BOPJ` |
| Córdoba | https://bop.dipucordoba.es | ✅ `BOPCO` |
| Sevilla | https://bopsevilla.dipusevilla.es | ✅ `BOPS` |
| Almería | http://www.bop.almeria.es | ❌ (web JS/OCR, aparcado) |
