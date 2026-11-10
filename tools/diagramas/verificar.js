// Verifica os diagramas ```mermaid da wiki (python tools/dev.py diagramas).
//
// O Material for MkDocs carrega o Mermaid 11 (unpkg.com/mermaid@11) e encolhe o SVG para caber na coluna do artigo
// (~690 px numa tela comum). Aqui cada diagrama é renderizado com o Mermaid 11 numa coluna dessa largura, e o script
// falha se algum não renderizar ou se a escala ficar abaixo de ESCALA_MIN (a letra ficaria menor que ~12 px).
//
// Uso: node verificar.js [--png <pasta>] [--largura 690] [--escala-min 0.75]
// O Chrome vem de CHROME_PATH ou dos caminhos usuais (Linux, Windows, macOS).
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const RAIZ = path.resolve(__dirname, '..', '..');
const DOCS = path.join(RAIZ, 'wiki', 'docs');
const arg = (nome, padrao) => {
  const i = process.argv.indexOf(nome);
  return i >= 0 ? process.argv[i + 1] : padrao;
};
const PASTA_PNG = arg('--png', null);
const LARGURA = Number(arg('--largura', '690'));
const ESCALA_MIN = Number(arg('--escala-min', '0.75'));

function chrome() {
  const candidatos = [process.env.CHROME_PATH, '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
  const achado = candidatos.find((c) => c && fs.existsSync(c));
  if (!achado) throw new Error('Chrome não encontrado: defina CHROME_PATH');
  return achado;
}

function paginas(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? paginas(p) : e.name.endsWith('.md') ? [p] : [];
  });
}

function diagramas() {
  const saida = [];
  for (const arquivo of paginas(DOCS).sort()) {
    const linhas = fs.readFileSync(arquivo, 'utf8').split('\n');
    for (let i = 0; i < linhas.length; i++) {
      const m = linhas[i].match(/^(\s*)```mermaid\s*$/);
      if (!m) continue;
      const recuo = m[1].length;
      const corpo = [];
      let j = i + 1;
      while (j < linhas.length && !/^\s*```\s*$/.test(linhas[j])) corpo.push(linhas[j++].slice(recuo));
      saida.push({ arquivo: path.relative(DOCS, arquivo).split(path.sep).join('/'), linha: i + 1, codigo: corpo.join('\n') });
      i = j;
    }
  }
  return saida;
}

(async () => {
  const lista = diagramas();
  const mermaid = fs.readFileSync(require.resolve('mermaid/dist/mermaid.min.js'), 'utf8');
  const navegador = await puppeteer.launch({ executablePath: chrome(), args: ['--no-sandbox'] });
  const pagina = await navegador.newPage();
  await pagina.setViewport({ width: 1400, height: 900, deviceScaleFactor: 1 });
  await pagina.setContent(`<html><body style="margin:0;font-family:Roboto,Arial,sans-serif;font-size:16px">
    <div id="col" style="width:${LARGURA}px"></div><div id="nat" style="display:inline-block"></div></body></html>`);
  await pagina.addScriptTag({ content: mermaid });
  await pagina.evaluate(() => mermaid.initialize({ startOnLoad: false }));
  if (PASTA_PNG) fs.mkdirSync(PASTA_PNG, { recursive: true });
  let falhas = 0;
  for (const d of lista) {
    const r = await pagina.evaluate(async (codigo) => {
      const col = document.getElementById('col');
      const nat = document.getElementById('nat');
      col.innerHTML = '';
      nat.innerHTML = '';
      try {
        const { svg } = await mermaid.render('d' + Math.random().toString(36).slice(2), codigo);
        col.innerHTML = svg;
        nat.innerHTML = svg;
        const s = nat.querySelector('svg');
        const vb = s.viewBox.baseVal;
        s.style.maxWidth = 'none';
        s.setAttribute('width', vb.width);
        s.setAttribute('height', vb.height);
        const escala = Math.min(1, col.querySelector('svg').getBoundingClientRect().width / vb.width);
        return { ok: true, largura: Math.round(vb.width), altura: Math.round(vb.height), escala };
      } catch (e) {
        return { ok: false, erro: String((e && e.message) || e).split('\n').slice(0, 4).join(' ') };
      }
    }, d.codigo);
    const onde = `${d.arquivo}:${d.linha}`;
    if (!r.ok) {
      falhas++;
      console.log(`ERRO      ${onde}  ${r.erro}`);
      continue;
    }
    const pequeno = r.escala < ESCALA_MIN;
    if (pequeno) falhas++;
    console.log(`${pequeno ? 'PEQUENO' : 'ok     '}   ${onde}  escala ${r.escala.toFixed(2)} (${r.largura}x${r.altura} px)`);
    if (PASTA_PNG) {
      const nome = onde.replace(/[/:]/g, '_').replace(/\.md_/, '_L');
      await (await pagina.$('#col')).screenshot({ path: path.join(PASTA_PNG, nome + '.png') });
    }
  }
  await navegador.close();
  console.log(`${lista.length} diagrama(s), ${falhas} com problema (escala mínima ${ESCALA_MIN} numa coluna de ${LARGURA} px)`);
  process.exit(falhas ? 1 : 0);
})().catch((e) => {
  console.error(e.message || e);
  process.exit(2);
});
