'use strict';
/* Axtel — painel. JavaScript puro, sem bibliotecas externas (funciona sem internet). */

// ------------------------------------------------------------------ utilidades
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
async function api(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}
const post = (url, corpo) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo || {}) });
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const enc = encodeURIComponent;

function fmtVolta(ms) {
  if (ms == null) return '—';
  const m = Math.floor(ms / 60000);
  const s = (ms % 60000) / 1000;
  return m + ':' + s.toFixed(3).padStart(6, '0');
}
function fmtDelta(ms) {
  if (ms == null) return '—';
  const sinal = ms > 0 ? '+' : ms < 0 ? '−' : '±';
  return sinal + (Math.abs(ms) / 1000).toFixed(3);
}
const fmtParcial = (ms) => (ms == null ? '—' : ms >= 60000 ? fmtVolta(ms) : (ms / 1000).toFixed(3));
function fmtDur(s) {
  s = Math.round(s || 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}min` : `${m} min`;
}
function fmtData(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' +
    d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function fmtDataLonga(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }) + ', ' +
    d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;
const km = (v) => (v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' km';
function guardar(chave, valor) { try { localStorage.setItem(chave, JSON.stringify(valor)); } catch (e) { /* sem armazenamento */ } }
function recuperar(chave, padrao) { try { const v = localStorage.getItem(chave); return v ? JSON.parse(v) : padrao; } catch (e) { return padrao; } }

// ------------------------------------------------------------------ estado
const E = {
  tok: 0, status: null, evento: null, sel: {}, sessao: null, combo: {}, painelAberto: false,
  pararPagina: null, spotter: recuperar('axtel.spotter', null), ultimoFalado: undefined,
};

// ------------------------------------------------------------------ rotas
function lerRota() {
  const h = location.hash.replace(/^#/, '') || '/';
  const [cam, qs] = h.split('?');
  const partes = cam.split('/').filter(Boolean).map(decodeURIComponent);
  return { nome: partes[0] || 'inicio', arg: partes.slice(1), q: Object.fromEntries(new URLSearchParams(qs || '')) };
}

const PAGINAS = {};
const NAV_DE = { inicio: 'inicio', jogo: 'jogo', sessoes: 'sessoes', sessao: 'sessoes', comparar: 'sessoes', aovivo: 'aovivo', calendario: 'calendario',
  pendencias: 'anotacoes', anotacoes: 'anotacoes', setups: 'setups', desafios: 'desafios', spotter: 'spotter', config: 'config' };
const ORDEM_NAV = [['inicio', 'Início', '#/'], ['jogo', 'Estatísticas por jogo', '#/jogo'], ['sessoes', 'Sessões', '#/sessoes'],
  ['calendario', 'Calendário', '#/calendario'], ['setups', 'Setups', '#/setups'], ['desafios', 'Desafios e plano', '#/desafios'],
  ['anotacoes', 'Anotações', '#/anotacoes'], ['aovivo', 'Ao vivo', '#/aovivo'], ['spotter', 'Spotter', '#/spotter'], ['config', 'Configurações', '#/config']];
function barraNav(nome) {
  if (nome === 'inicio') return '';
  return `<div class="barra-nav"><button class="btn" data-acao="voltar">← Voltar</button></div>`;
}

async function render(manterRolagem) {
  const r = lerRota();
  const tok = ++E.tok;
  if (E.pararPagina) { E.pararPagina(); E.pararPagina = null; }
  $$('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.rota === (NAV_DE[r.nome] || '')));
  const pagina = PAGINAS[r.nome] || PAGINAS.inicio;
  desenharAtalhoSpotter();
  const area = $('#conteudo');
  const y = area.scrollTop;
  try {
    const html = await pagina.html(r);
    if (tok !== E.tok) return; // o usuário já foi para outra página
    $('#conteudo').innerHTML = barraNav(r.nome) + html;
    if (pagina.depois) pagina.depois(r);
    area.scrollTop = manterRolagem ? y : 0;
  } catch (e) {
    if (tok !== E.tok) return;
    console.error(e);
    $('#conteudo').innerHTML = `<div class="cartao"><h2>Não consegui carregar esta página</h2>
      <p class="fraco">O Axtel está aberto? Confira a janela preta do Axtel. (${esc(e.message)})</p>
      <button class="btn" data-acao="recarregar">Tentar de novo</button></div>`;
  }
}
window.addEventListener('hashchange', () => { E.navegou = true; render(false); });

// ------------------------------------------------------------------ gráficos (SVG simples)
function grafico({ series, ymin, ymax, altura = 160, xmax = 1, zero = false, fmtY = (v) => v, idCursor = null, rotulosX = null }) {
  const W = 1000, H = altura;
  const ys = series.flatMap((s) => s.pts.map((p) => p[1])).filter((v) => v != null && isFinite(v));
  if (!ys.length) return '<div class="fraco">Sem dados para o gráfico.</div>';
  let lo = ymin ?? Math.min(...ys), hi = ymax ?? Math.max(...ys);
  if (zero) { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; lo = -m; hi = m; }
  if (hi === lo) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const X = (x) => (x / xmax) * W;
  const Y = (y) => H - ((y - lo) / (hi - lo)) * H;
  const caminhos = series.map((s) => {
    const d = s.pts.filter((p) => p[1] != null && isFinite(p[1]))
      .map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('');
    return `<path d="${d}" fill="none" stroke="${s.cor}" stroke-width="${s.largura || 2}" ${s.tracejado ? 'stroke-dasharray="6 5"' : ''} vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`;
  }).join('');
  const linhas = [0, 0.5, 1].map((f) => lo + pad + (hi - lo - 2 * pad) * f);
  const grade = linhas.map((v) => `<line x1="0" x2="${W}" y1="${Y(v)}" y2="${Y(v)}" stroke="#252C36" vector-effect="non-scaling-stroke"/>`).join('');
  const linhaZero = zero ? `<line x1="0" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="#56606E" vector-effect="non-scaling-stroke"/>` : '';
  const cursor = idCursor ? `<line id="${idCursor}" x1="-10" x2="-10" y1="0" y2="${H}" stroke="#E7EAEE" stroke-opacity=".5" vector-effect="non-scaling-stroke"/>` : '';
  const rot = linhas.map((v) => `<div style="position:absolute;left:0;top:${(Y(v) / H) * 100}%;transform:translateY(-50%);font-size:11px" class="fraco mono">${esc(fmtY(v))}</div>`).join('');
  const rx = rotulosX ? `<div class="linha fraco" style="justify-content:space-between;font-size:11px;margin:4px 0 0 64px">${rotulosX.map((t) => `<span>${esc(t)}</span>`).join('')}</div>` : '';
  return `<div style="position:relative;padding-left:64px">
      <div style="position:absolute;left:0;top:0;bottom:0;width:60px">${rot}</div>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px;display:block">${grade}${linhaZero}${caminhos}${cursor}</svg>
    </div>${rx}`;
}

// ------------------------------------------------------------------ indicador de status
function desenharIndicador() {
  const s = E.status;
  const ponto = $('#ind-ponto'), txt = $('#ind-txt'), cont = $('#ind-cont');
  if (!s) {
    ponto.className = 'ponto vermelho';
    txt.textContent = 'Axtel fechado';
  } else {
    ponto.className = 'ponto ' + s.nivel;
    txt.textContent = s.titulo;
    cont.hidden = !s.pendentes;
    cont.textContent = s.pendentes;
    $('#rodape').textContent = `Axtel ${s.versao}`;
  }
  if (E.painelAberto) desenharPainelStatus();
}

function desenharPainelStatus() {
  const p = $('#ind-painel');
  const s = E.status;
  if (!$('#ind-p-tit', p)) {
    p.innerHTML = `<h3 id="ind-p-tit"></h3><div class="fraco" id="ind-p-det"></div><div class="fraco" style="font-size:12px;margin-top:4px" id="ind-p-desde"></div>
      <hr><b>Alertas</b><div id="ind-p-alertas"></div>
      <hr><b>Relatar um problema</b>
      <p class="fraco" style="margin:4px 0 8px;font-size:12.5px">Descreva o que aconteceu. O Axtel salva um pacote com o log e os dados do jogo para analisarmos.</p>
      <textarea id="rel-texto" placeholder="Ex.: a volta 5 não apareceu na sessão"></textarea>
      <div class="linha" style="margin-top:8px"><button class="btn pri" data-acao="relatorio-enviar">Salvar relatório</button></div>
      <div id="rel-res" class="fraco" style="font-size:12.5px;margin-top:8px;word-break:break-all"></div>`;
  }
  if (!s) {
    $('#ind-p-tit', p).textContent = 'Sem conexão com o Axtel';
    $('#ind-p-det', p).textContent = 'A janela do Axtel foi fechada. Abra o Axtel de novo pelo atalho.';
    $('#ind-p-desde', p).textContent = '';
    $('#ind-p-alertas', p).innerHTML = '';
    return;
  }
  $('#ind-p-tit', p).innerHTML = `<span class="ponto ${s.nivel}" style="display:inline-block;margin-right:8px"></span>${esc(s.titulo)}`;
  $('#ind-p-det', p).textContent = s.detalhe || '';
  const min = Math.max(0, Math.round((Date.now() / 1000 - s.desde) / 60));
  $('#ind-p-desde', p).textContent = (min < 1 ? 'agora há pouco' : `há ${plural(min, 'minuto', 'minutos')}`) + (s.gravando ? ' · gravando' : '');
  $('#ind-p-alertas', p).innerHTML = s.alertas.length ? s.alertas.slice(0, 8).map((a) => `
    <div class="alerta ${a.nivel} ${a.resolvido ? 'res' : ''}">
      <div>${esc(a.texto)}</div>
      <div class="linha" style="margin-top:4px"><span class="fraco" style="font-size:11px">${fmtData(a.quando)}</span><span class="esp"></span>
      ${a.resolvido ? '<span class="fraco" style="font-size:11px">resolvido</span>' : `<button class="btn" style="padding:2px 8px;font-size:12px" data-acao="alerta-resolver" data-id="${a.id}">Marcar como resolvido</button>`}</div>
    </div>`).join('') : '<div class="fraco" style="font-size:12.5px;margin-top:4px">Nenhum alerta.</div>';
}

function abrirPainel(abrir) {
  E.painelAberto = abrir;
  $('#ind-painel').hidden = !abrir;
  $('.ind-btn').setAttribute('aria-expanded', String(abrir));
  if (abrir) desenharPainelStatus();
}

async function lerStatus() {
  try {
    E.status = await api('/api/status');
  } catch (e) {
    E.status = null;
  }
  desenharIndicador();
  if (!E.status) return;
  // volta nova gravada: atualiza a página aberta e fala no spotter
  const ev = E.status.evento;
  if (E.evento !== null && ev !== E.evento) {
    const r = lerRota();
    if (['inicio', 'jogo', 'sessoes', 'sessao'].includes(r.nome)) render(true);
  }
  E.evento = ev;
  spotterVerificar();
}

// ------------------------------------------------------------------ spotter (voz)
// Catálogo dos avisos: id, nome, descrição, modos em que fala (s = só o essencial, n = normal, f = tudo), selo
const AVISOS = [
  ['tempo', 'Tempo de volta', 'Ao cruzar a linha, o tempo da volta que acabou.', 'nf', ''],
  ['recorde', 'Recorde pessoal', 'Quando bate a sua melhor volta naquele carro e pista.', 'snf', 'essencial'],
  ['sessao', 'Melhor volta da sessão', 'Quando a volta é a mais rápida do dia, mesmo sem ser recorde.', 'nf', ''],
  ['invalida', 'Volta inválida', 'Corte de pista, pneus fora ou incidente: avisa na hora.', 'snf', 'essencial'],
  ['setor', 'Parciais', 'Em cada terço da volta: ganhou ou perdeu contra a melhor da sessão.', 'f', ''],
  ['ritmo', 'Ritmo', 'A cada 3 voltas válidas, a média comparada com a melhor.', 'nf', ''],
  ['combustivel', 'Combustível', 'Quando restam 5 voltas ou menos de combustível.', 'snf', 'essencial'],
  ['boxes', 'Boxes', 'Ao entrar nos boxes.', 'nf', ''],
];
const LINGUAS = { pt: 'Português (Brasil)', en: 'English', es: 'Español' };
const TAG = { pt: 'pt-BR', en: 'en-US', es: 'es-419' };
const SP = { cfg: null, ultimoEv: null, fila: [], ocupado: false, ultimo: '', ultimoQuando: 0, silencioVolta: null,
  historico: recuperar('axtel.falados', []), voz: null, salvarTimer: null, bloqueado: false };

function linguaDetectada() {
  const l = (navigator.language || 'pt-BR').toLowerCase();
  return l.startsWith('pt') ? 'pt' : l.startsWith('es') ? 'es' : 'en';
}
const spLingua = () => (!SP.cfg || SP.cfg.lingua === 'auto' ? linguaDetectada() : SP.cfg.lingua);
const ehCelular = () => window.matchMedia('(pointer: coarse)').matches && window.innerWidth < 900;
function spDeveTocarAqui() {
  const s = SP.cfg ? SP.cfg.saida : 'ambos';
  return s === 'ambos' || (s === 'celular') === ehCelular();
}
function spAvisoLigado(id) {
  if (!SP.cfg) return false;
  const a = AVISOS.find((x) => x[0] === id);
  const letra = SP.cfg.modo === 'silencioso' ? 's' : SP.cfg.modo === 'falador' ? 'f' : 'n';
  return !!a && a[3].includes(letra) && !(SP.cfg.desligados || []).includes(id);
}
function spSalvar(mud) {
  Object.assign(SP.cfg, mud);
  clearTimeout(SP.salvarTimer);
  SP.salvarTimer = setTimeout(() => post('/api/config', { spotter: SP.cfg }), 400);
  desenharAtalhoSpotter();
}
function desenharAtalhoSpotter() {
  const a = $('#atalho-spotter'), e = $('#spot-estado');
  if (!a || !SP.cfg) return;
  a.classList.toggle('off', !SP.cfg.ligado);
  a.classList.toggle('on', lerRota().nome === 'spotter');
  e.textContent = !SP.cfg.ligado ? 'desligado' : SP.silencioVolta !== null ? 'em silêncio' : 'ligado';
}

// ---- frases
function tempoFalado(ms, l) {
  const m = Math.floor(ms / 60000), s = ((ms % 60000) / 1000).toFixed(1);
  if (l === 'en') return (m ? `${m} ` : '') + s;
  return (m ? `${m} ${l === 'es' ? 'y' : 'e'} ` : '') + s.replace('.', ',');
}
function deltaFalado(ms, l) {
  const a = Math.abs(ms), mais = ms > 0;
  if (a < 50) return { pt: 'igual à melhor', en: 'matching your best', es: 'igual a tu mejor' }[l];
  let q;
  if (a < 1000) {
    const d = Math.max(1, Math.round(a / 100));
    q = l === 'en' ? `${d} tenth${d > 1 ? 's' : ''}` : l === 'es' ? `${d} décima${d > 1 ? 's' : ''}` : `${d === 1 ? 'um' : d} décimo${d > 1 ? 's' : ''}`;
  } else {
    const s = (a / 1000).toFixed(1);
    q = l === 'en' ? `${s} seconds` : `${s.replace('.', ',')} segundo${a >= 2000 ? 's' : ''}`;
  }
  return l === 'en' ? `${q} ${mais ? 'down' : 'up'}` : l === 'es' ? `${q} ${mais ? 'más lento' : 'más rápido'}` : `${q} ${mais ? 'mais lento' : 'mais rápido'}`;
}
function motivoCurto(m, l) {
  if (!m) return '';
  if (/pneus|pista/i.test(m)) return { pt: 'Saiu da pista.', en: 'Track limits.', es: 'Fuera de pista.' }[l];
  if (/incidente/i.test(m)) return { pt: 'Incidente.', en: 'Incident.', es: 'Incidente.' }[l];
  return '';
}
// devolve [id do aviso, frase] ou null
function fraseEvento(ev, l) {
  const T = (pt, en, es) => (l === 'en' ? en : l === 'es' ? es : pt);
  switch (ev.tipo) {
    case 'volta':
      if (!ev.valida) return null; // a volta inválida já foi avisada na hora
      if (ev.recorde_pessoal && spAvisoLigado('recorde')) return ['recorde', T(`Recorde pessoal! ${tempoFalado(ev.tempo_ms, l)}.`, `Personal best! ${tempoFalado(ev.tempo_ms, l)}.`, `¡Récord personal! ${tempoFalado(ev.tempo_ms, l)}.`)];
      if (ev.recorde_sessao && spAvisoLigado('sessao')) return ['sessao', T(`Melhor volta da sessão. ${tempoFalado(ev.tempo_ms, l)}.`, `Best lap of the session. ${tempoFalado(ev.tempo_ms, l)}.`, `Mejor vuelta de la sesión. ${tempoFalado(ev.tempo_ms, l)}.`)];
      return ['tempo', T(`Volta ${ev.numero}. ${tempoFalado(ev.tempo_ms, l)}.`, `Lap ${ev.numero}. ${tempoFalado(ev.tempo_ms, l)}.`, `Vuelta ${ev.numero}. ${tempoFalado(ev.tempo_ms, l)}.`)];
    case 'invalida': return ['invalida', T('Volta inválida. ', 'Lap invalidated. ', 'Vuelta inválida. ') + motivoCurto(ev.motivo, l)];
    case 'parcial': return ['setor', T(`Parcial ${ev.parcial}: `, `Split ${ev.parcial}: `, `Parcial ${ev.parcial}: `) + deltaFalado(ev.delta_ms, l) + '.'];
    case 'ritmo': return ['ritmo', T('Ritmo das últimas 3: ', 'Pace over the last 3: ', 'Ritmo de las últimas 3: ') + deltaFalado(ev.delta_ms, l) + '.'];
    case 'combustivel':
      if (ev.voltas > 5) return null;
      return ['combustivel', T(`Combustível para mais ${Math.floor(ev.voltas)} voltas.`, `Fuel for ${Math.floor(ev.voltas)} more laps.`, `Combustible para ${Math.floor(ev.voltas)} vueltas más.`)];
    case 'boxes': return ['boxes', T('Entrada dos boxes. Limitador.', 'Pit entry. Limiter.', 'Entrada a boxes. Limitador.')];
    default: return null;
  }
}
const EXEMPLOS = {
  tempo: { volta: 1, numero: 12, valida: true, tempo_ms: 102700, tipo: 'volta' },
  recorde: { tipo: 'volta', numero: 17, valida: true, tempo_ms: 102301, recorde_pessoal: true },
  sessao: { tipo: 'volta', numero: 9, valida: true, tempo_ms: 102540, recorde_sessao: true },
  invalida: { tipo: 'invalida', motivo: 'Saiu da pista (3 ou mais pneus fora)' },
  setor: { tipo: 'parcial', parcial: 2, delta_ms: -200 },
  ritmo: { tipo: 'ritmo', delta_ms: 300 },
  combustivel: { tipo: 'combustivel', voltas: 4 },
  boxes: { tipo: 'boxes' },
};
function fraseExemplo(id, l) {
  const ev = EXEMPLOS[id];
  const salvo = SP.cfg.desligados; SP.cfg.desligados = [];
  const modo = SP.cfg.modo; SP.cfg.modo = 'falador';
  const f = fraseEvento(ev, l);
  SP.cfg.desligados = salvo; SP.cfg.modo = modo;
  return f ? f[1] : '';
}

// ---- liberação do som: o navegador só deixa tocar depois de um clique ou tecla na página.
// No primeiro clique tocamos um som mudo num player que fica guardado e é usado em todas as falas.
const SOM = { el: null, liberado: false };
const SOM_MUDO = 'data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YSADAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==';
function liberarSom() {
  try {
    if (!SOM.el) SOM.el = new Audio();
    SOM.el.src = SOM_MUDO;
    const p = SOM.el.play();
    if (p && p.then) p.then(() => { SOM.liberado = true; SP.bloqueado = false; const a = $('#aviso-som'); if (a) a.hidden = true; }).catch(() => {});
  } catch (e) { /* sem som neste navegador */ }
  try {
    if ('speechSynthesis' in window) { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; speechSynthesis.speak(u); }
  } catch (e) { /* idem */ }
}
['pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, () => { if (!SOM.liberado) liberarSom(); }, { capture: true }));

// ---- voz: ElevenLabs pelo Axtel; sem ela, a voz mais natural do navegador
function melhorVozNavegador(l) {
  if (!('speechSynthesis' in window)) return null;
  const tag = TAG[l];
  const vs = speechSynthesis.getVoices().filter((v) => v.lang && v.lang.replace('_', '-').toLowerCase().startsWith(l));
  const escolhida = recuperar('axtel.voz.navegador.' + l, '');
  const fixa = vs.find((v) => v.name === escolhida);
  if (fixa) return fixa;
  return vs.find((v) => v.lang.replace('_', '-').toLowerCase() === tag.toLowerCase()) || vs[0] || null;
}
function falarNavegador(texto, l) {
  return new Promise((ok) => {
    if (!('speechSynthesis' in window)) return ok(false);
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = TAG[l]; u.rate = (SP.cfg.ritmo || 105) / 100; u.volume = (SP.cfg.volume ?? 80) / 100;
    const v = melhorVozNavegador(l); if (v) u.voice = v;
    u.onend = () => ok(true); u.onerror = () => ok(false);
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
    setTimeout(() => ok(true), 15000);
  });
}
async function falarElevenLabs(texto, l) {
  try {
    const r = await post('/api/voz', { texto, lingua: l });
    if (!r.ok) { SP.voz = r.erro; return false; }
    const a = SOM.el || new Audio();
    a.onended = a.onerror = null;
    a.src = r.url;
    a.volume = (SP.cfg.volume ?? 80) / 100;
    a.playbackRate = (SP.cfg.ritmo || 100) / 100;
    a.preservesPitch = true;
    await a.play();
    SP.voz = 'ElevenLabs';
    SP.bloqueado = false; $('#aviso-som').hidden = true;
    await new Promise((ok) => { a.onended = ok; a.onerror = ok; setTimeout(ok, 20000); });
    return true;
  } catch (e) {
    if (e && e.name === 'NotAllowedError') { SP.bloqueado = true; $('#aviso-som').hidden = false; return 'bloqueado'; }
    return false;
  }
}
async function falar(texto, { forcar = false, registrar = true, tipo = '' } = {}) {
  if (!texto || !SP.cfg) return;
  if (!forcar && (!SP.cfg.ligado || !spDeveTocarAqui())) return;
  const l = spLingua();
  let r = await falarElevenLabs(texto, l);
  if (r === false) { await falarNavegador(texto, l); SP.voz = 'navegador'; r = true; }
  SP.ultimo = texto; SP.ultimoQuando = Date.now();
  if (registrar) {
    SP.historico.unshift({ quando: new Date().toISOString(), texto, tipo });
    SP.historico = SP.historico.slice(0, 30);
    guardar('axtel.falados', SP.historico);
    if ($('#falados')) desenharFalados();
  }
  if ($('#sp-ultimo')) { $('#sp-ultimo').textContent = '“' + texto + '”'; $('#sp-voz-usada').textContent = SP.voz === 'ElevenLabs' ? 'Voz: ElevenLabs' : 'Voz: navegador' + (SP.voz && SP.voz !== 'navegador' ? ` (${SP.voz})` : ''); }
}

// espera uma reta: acelerador cheio e sem freio (até 6 s), e respeita o intervalo mínimo
async function esperarMomento(prioridade) {
  const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const falta = (SP.cfg.intervalo || 4) * 1000 - (Date.now() - SP.ultimoQuando);
  if (falta > 0 && !prioridade) await espera(falta);
  if (prioridade || (!SP.cfg.retas && !SP.cfg.freada)) return;
  const fim = Date.now() + 6000;
  while (Date.now() < fim) {
    try {
      const v = await api('/api/aovivo');
      if (!v.jogo) return;
      const freando = v.freio > 0.05, reta = v.acel > 0.85 && !freando;
      if ((SP.cfg.retas ? reta : true) && (SP.cfg.freada ? !freando : true)) return;
    } catch (e) { return; }
    await espera(250);
  }
}
async function processarFila() {
  if (SP.ocupado) return;
  SP.ocupado = true;
  try {
    while (SP.fila.length) {
      const [id, frase, prio] = SP.fila.shift();
      await esperarMomento(prio);
      await falar(frase, { tipo: id });
    }
  } finally { SP.ocupado = false; }
}
function spComando(acao) {
  if (acao === 'repetir') { if (SP.ultimo) falar(SP.ultimo, { forcar: true, registrar: false }); }
  else if (acao === 'silenciar') { SP.silencioVolta = SP.silencioVolta === null ? (E.status && E.status.evento) || 0 : null; desenharAtalhoSpotter(); if (lerRota().nome === 'spotter') render(true); }
  else if (acao === 'alternar') { spSalvar({ ligado: !SP.cfg.ligado }); if (lerRota().nome === 'spotter') render(true); }
}
async function spotterVerificar() {
  if (!SP.cfg) return;
  let r;
  try { r = await api('/api/eventos?depois=' + (SP.ultimoEv ?? 0)); } catch (e) { return; }
  if (SP.ultimoEv === null) { SP.ultimoEv = r.ultimo; return; } // ao abrir o painel, não repete avisos antigos
  SP.ultimoEv = r.ultimo;
  const l = spLingua();
  for (const ev of r.eventos) {
    if (ev.tipo === 'comando') { spComando(ev.acao); continue; }
    if (ev.tipo === 'volta' && SP.silencioVolta !== null && E.status && E.status.evento > SP.silencioVolta) { SP.silencioVolta = null; desenharAtalhoSpotter(); }
    const f = fraseEvento(ev, l);
    if (!f || !spAvisoLigado(f[0])) continue;
    const essencial = ['recorde', 'invalida', 'combustivel'].includes(f[0]);
    if (SP.silencioVolta !== null && !essencial) continue;
    SP.fila.push([f[0], f[1], SP.cfg.prioridade && essencial && f[0] !== 'recorde']);
  }
  processarFila();
}
function desenharFalados() {
  const el = $('#falados');
  if (!el) return;
  el.innerHTML = SP.historico.length ? SP.historico.slice(0, 15).map((l, i) => `<div class="linha" style="padding:6px 0;border-bottom:1px solid #1D232C">
      <button class="btn" style="padding:3px 9px" data-acao="falar-log" data-i="${i}" aria-label="Ouvir de novo">▶</button>
      <span class="mono fraco" style="width:46px">${new Date(l.quando).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
      <span style="flex:1;min-width:0">“${esc(l.texto)}”</span></div>`).join('')
    : '<div class="fraco">Ainda não houve avisos. Eles aparecem aqui durante a corrida.</div>';
}
async function carregarSpotter() {
  try { SP.cfgGeral = await api('/api/config'); SP.cfg = SP.cfgGeral.spotter; } catch (e) { SP.cfg = null; }
  desenharAtalhoSpotter();
}

// ------------------------------------------------------------------ INÍCIO
PAGINAS.inicio = {
  async html() {
    const d = await api('/api/resumo');
    const t = d.totais;
    if (!t.sessoes) {
      return `<h1>Início</h1><p class="sub">Seus dados de todos os jogos, juntos.</p>
        <div class="cartao vazio-grande">
          <h2>Nenhuma sessão gravada ainda</h2>
          <p class="fraco">O Axtel está pronto. É só ir para a pista que ele grava sozinho.</p>
          <div class="passos">
            <div><b>1</b><br>Deixe o Axtel aberto (a janela preta pode ficar minimizada).</div>
            <div><b>2</b><br>Abra o jogo e entre na pista. O ponto lá em cima fica <span class="verde">verde</span>.</div>
            <div><b>3</b><br>Cada volta completa aparece aqui na hora, separada por jogo.</div>
          </div>
          <p class="fraco" style="margin-top:22px">Jogos que esta versão lê: ${d.suportados.map(esc).join(', ')}.<br>Em breve: ${d.futuros.map(esc).join(', ')}.</p>
          <div class="linha" style="justify-content:center;margin-top:10px"><a class="btn pri" href="#/aovivo">Ver tela Ao vivo</a></div>
        </div>`;
    }
    const maxT = Math.max(...d.por_jogo.map((j) => j.tempo_s), 1);
    const maxS = Math.max(...d.semanas.map((s) => s.sessoes), 1);
    const semDados = d.suportados.filter((j) => !d.por_jogo.some((p) => p.jogo === j));
    return `<h1>Início</h1><p class="sub">Seus dados de todos os jogos, juntos.</p>
      <div class="kpis">
        <div class="kpi"><small>Sessões</small><b>${t.sessoes}</b></div>
        <div class="kpi"><small>Voltas</small><b>${t.voltas}</b><span>${t.validas} válidas</span></div>
        <div class="kpi"><small>Tempo na pista</small><b>${fmtDur(t.tempo_s)}</b></div>
        <div class="kpi"><small>Distância</small><b>${km(t.distancia_km)}</b></div>
        <div class="kpi"><small>Recordes pessoais</small><b class="roxo">${t.recordes}</b></div>
      </div>
      <div class="cartao escolha"><h2>Escolha o jogo para ver as estatísticas</h2>
        <div class="chips">
          ${d.por_jogo.map((j) => `<a class="chip" href="#/jogo/${enc(j.jogo)}"><b>${esc(j.jogo)}</b><small>${plural(j.sessoes, 'sessão', 'sessões')} · ${fmtDur(j.tempo_s)}</small><small>última: ${fmtData(j.ultima)}</small></a>`).join('')}
          ${semDados.map((j) => `<a class="chip vazio" href="#/jogo/${enc(j)}"><b>${esc(j)}</b><small>sem sessões ainda</small></a>`).join('')}
        </div>
      </div>
      <div class="grade g2">
        <div class="cartao"><h2>Tempo por jogo</h2><div class="barras">
          ${d.por_jogo.map((j) => `<div class="barra"><span>${esc(j.jogo)}</span><div class="trilho"><i style="width:${(j.tempo_s / maxT) * 100}%"></i></div><span class="fraco mono">${fmtDur(j.tempo_s)}</span></div>`).join('')}
        </div></div>
        <div class="cartao"><h2>Sessões por semana</h2><div class="colunas">
          ${d.semanas.map((s) => `<div title="${s.sessoes} na semana de ${new Date(s.semana + 'T12:00').toLocaleDateString('pt-BR')}"><small>${s.sessoes || ''}</small><i style="height:${(s.sessoes / maxS) * 100}%"></i><small>${new Date(s.semana + 'T12:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}</small></div>`).join('')}
        </div></div>
      </div>
      <div class="grade g2">
        <div class="cartao"><h2>Últimas sessões</h2>${tabelaSessoesCurta(d.recentes)}</div>
        <div class="cartao"><h2>Recordes recentes</h2>${d.recordes.length ? `<table><tbody>${d.recordes.map((s) => `
          <tr class="clica" data-ir="#/sessao/${s.id}"><td><b>${esc(s.carro)}</b><br><span class="fraco">${esc(s.pista)} · ${esc(s.jogo)}</span></td>
          <td class="mono roxo">${fmtVolta(s.melhor_ms)}</td><td class="fraco">${fmtData(s.inicio)}</td></tr>`).join('')}</tbody></table>` : '<div class="fraco">Nenhum ainda.</div>'}</div>
      </div>`;
  },
};

function tabelaSessoesCurta(ss) {
  return `<div class="rolar"><table><tbody>${ss.map((s) => `
    <tr class="clica" data-ir="#/sessao/${s.id}">
      <td class="fraco">${fmtData(s.inicio)}</td>
      <td><b>${esc(s.carro)}</b><br><span class="fraco">${esc(s.pista)} · ${esc(s.jogo)} · ${esc(s.tipo)}</span></td>
      <td class="mono">${fmtVolta(s.melhor_ms)} ${s.recorde ? '<span class="selo pb">recorde</span>' : ''}</td>
      <td style="text-align:right"><a href="#/sessao/${s.id}" class="fraco">Abrir ›</a></td>
    </tr>`).join('')}</tbody></table></div>`;
}

// ------------------------------------------------------------------ ESTATÍSTICAS POR JOGO
PAGINAS.jogo = {
  async html(r) {
    const j = await api('/api/jogos');
    let nome = r.arg[0];
    if (!nome) {
      nome = j.com_dados[0] || j.suportados[0];
      history.replaceState(null, '', '#/jogo/' + enc(nome));
    }
    const lista = [...j.com_dados, ...j.suportados.filter((x) => !j.com_dados.includes(x))];
    if (!lista.includes(nome)) lista.push(nome);
    const escolha = `<div class="cartao escolha"><h2>Mostrar resultados de</h2><div class="chips">
      ${lista.map((x) => `<a class="chip ${x === nome ? 'on' : ''} ${j.com_dados.includes(x) ? '' : 'vazio'}" href="#/jogo/${enc(x)}"><b>${esc(x)}</b><small>${j.com_dados.includes(x) ? 'com dados' : 'sem sessões'}</small></a>`).join('')}
    </div></div>`;
    const d = await api('/api/jogo?nome=' + enc(nome));
    const t = d.totais;
    const topo = `<h1>Estatísticas por jogo</h1><p class="sub">Escolha o jogo e abra qualquer sessão para ver a telemetria.</p>${escolha}`;
    if (!t.sessoes) {
      return topo + `<div class="cartao vazio-grande"><h2>Nenhuma sessão de ${esc(nome)} ainda</h2>
        <p class="fraco">Abra o ${esc(nome)} com o Axtel aberto e complete algumas voltas.</p></div>`;
    }
    const ci = Math.min(E.combo[nome] ?? 0, d.combos.length - 1);
    const c = d.combos[ci];
    const evol = c.evolucao;
    const q = d.qualidade;
    return topo + `
      <div class="kpis">
        <div class="kpi"><small>Sessões</small><b>${t.sessoes}</b></div>
        <div class="kpi"><small>Voltas</small><b>${t.voltas}</b><span>${t.validas} válidas</span></div>
        <div class="kpi"><small>Tempo na pista</small><b>${fmtDur(t.tempo_s)}</b></div>
        <div class="kpi"><small>Distância</small><b>${km(t.distancia_km)}</b></div>
        <div class="kpi"><small>Recordes pessoais</small><b class="roxo">${t.recordes}</b></div>
      </div>
      <div class="cartao"><h2>Carros e pistas</h2><p class="fraco" style="margin:-6px 0 10px">Clique numa linha para ver a evolução daquela combinação.</p>
        <div class="rolar"><table><thead><tr><th>Carro</th><th>Pista</th><th>Sessões</th><th>Voltas</th><th>Melhor volta</th><th>Última vez</th><th></th></tr></thead><tbody>
        ${d.combos.map((x, i) => `<tr class="clica ${i === ci ? 'sel' : ''}" data-acao="combo" data-jogo="${esc(nome)}" data-i="${i}">
          <td><b>${esc(x.carro)}</b></td><td>${esc(x.pista)}</td><td>${x.sessoes}</td><td>${x.voltas}</td>
          <td class="mono roxo">${fmtVolta(x.melhor_ms)}</td><td class="fraco">${fmtData(x.ultima)}</td>
          <td>${x.melhor_sessao ? `<a class="btn" href="#/sessao/${x.melhor_sessao}">Sessão do recorde</a>` : ''}</td></tr>`).join('')}
        </tbody></table></div></div>
      <div class="cartao"><h2>Evolução · ${esc(c.carro)} em ${esc(c.pista)}</h2>
        ${evol.length >= 2 ? grafico({ series: [{ pts: evol.map((e, i) => [i, e.melhor_ms]), cor: 'var(--destaque)' }], xmax: Math.max(1, evol.length - 1), fmtY: fmtVolta, altura: 170,
          rotulosX: [fmtData(evol[0].inicio), fmtData(evol[evol.length - 1].inicio)] }) + '<p class="fraco" style="margin:8px 0 0;font-size:12px">Melhor volta de cada sessão. Quanto mais baixo, mais rápido.</p>'
          : '<div class="fraco">Faça pelo menos duas sessões com essa combinação para ver a evolução.</div>'}
      </div>
      <div class="grade g2">
        <div class="cartao"><h2>Tipos de sessão</h2><div class="barras">
          ${d.tipos.map((x) => `<div class="barra"><span>${esc(x.tipo)}</span><div class="trilho"><i style="width:${(x.sessoes / t.sessoes) * 100}%"></i></div><span class="fraco">${plural(x.sessoes, 'sessão', 'sessões')}</span></div>`).join('')}
        </div></div>
        <div class="cartao"><h2>Qualidade da pilotagem</h2>
          <div class="kpis" style="margin:0">
            <div class="kpi"><small>Voltas válidas</small><b>${q.pct_validas ?? '—'}%</b><span>${q.validas} de ${q.voltas}</span></div>
            <div class="kpi"><small>Consistência</small><b>${q.consistencia_ms != null ? '±' + (q.consistencia_ms / 1000).toFixed(3) : '—'}</b><span>variação média das voltas boas</span></div>
          </div></div>
      </div>
      <div class="cartao"><h2>Sessões de ${esc(nome)}</h2>${tabelaSessoes(d.sessoes, false)}</div>`;
  },
};

function tabelaSessoes(ss, mostrarJogo) {
  if (!ss.length) return '<div class="fraco">Nenhuma sessão com esse filtro.</div>';
  return `<div class="rolar"><table><thead><tr><th>Data</th>${mostrarJogo ? '<th>Jogo</th>' : ''}<th>Tipo</th><th>Carro</th><th>Pista</th><th>Voltas</th><th>Melhor</th><th>Duração</th><th></th></tr></thead><tbody>
    ${ss.map((s) => `<tr class="clica" data-ir="#/sessao/${s.id}">
      <td class="fraco">${fmtData(s.inicio)}${s.aberta ? ' <span class="selo ok">gravando</span>' : ''}</td>${mostrarJogo ? `<td>${esc(s.jogo)}</td>` : ''}
      <td>${esc(s.tipo)}</td><td><b>${esc(s.carro)}</b></td><td>${esc(s.pista)}</td>
      <td>${s.validas}<span class="fraco">/${s.voltas}</span></td>
      <td class="mono">${fmtVolta(s.melhor_ms)} ${s.recorde ? '<span class="selo pb">recorde</span>' : ''}</td>
      <td class="fraco">${fmtDur(s.tempo_s)}</td>
      <td><a class="btn" href="#/sessao/${s.id}">Abrir</a></td></tr>`).join('')}
  </tbody></table></div>`;
}

// ------------------------------------------------------------------ SESSÕES
PAGINAS.sessoes = {
  async html(r) {
    const jogo = r.q.jogo || '', tipo = r.q.tipo || '', data = r.q.data || '';
    const [j, d] = await Promise.all([api('/api/jogos'),
      api(`/api/sessoes?jogo=${enc(jogo)}&tipo=${enc(tipo)}&data=${enc(data)}`)]);
    const link = (jg, tp, dt = data) => '#/sessoes?' + new URLSearchParams({ ...(jg ? { jogo: jg } : {}), ...(tp ? { tipo: tp } : {}), ...(dt ? { data: dt } : {}) }).toString();
    const t = d.totais;
    return `<h1>Sessões</h1><p class="sub">Todas as sessões gravadas. Clique em uma para ver voltas, parciais e telemetria.</p>
      <div class="cartao escolha"><h2>Mostrar sessões de</h2>
        <div class="chips">
          <a class="chip ${!jogo ? 'on' : ''}" href="${link('', tipo)}"><b>Todos os jogos</b></a>
          ${j.com_dados.map((x) => `<a class="chip ${x === jogo ? 'on' : ''}" href="${link(x, '')}"><b>${esc(x)}</b></a>`).join('')}
        </div>
        <div class="linha" style="margin-top:12px"><label class="fraco" for="filtro-tipo">Tipo</label>
          <select class="campo" id="filtro-tipo" data-mudar="tipo" data-jogo="${esc(jogo)}" data-data="${esc(data)}">
            <option value="">Todos</option>${d.tipos.map((x) => `<option ${x === tipo ? 'selected' : ''}>${esc(x)}</option>`).join('')}
          </select>
          ${data ? `<span class="selo ok" style="font-size:12.5px;padding:4px 10px">Dia ${fmtDia(data)}</span><a class="btn" href="${link(jogo, tipo, '')}">Mostrar todos os dias</a><a class="btn" href="#/calendario/${data.slice(0, 7)}?dia=${data}">Ver no calendário</a>` : ''}</div>
      </div>
      ${t.sessoes ? `<div class="kpis">
        <div class="kpi"><small>Sessões</small><b>${t.sessoes}</b></div>
        <div class="kpi"><small>Voltas</small><b>${t.voltas}</b><span>${t.validas} válidas</span></div>
        <div class="kpi"><small>Tempo na pista</small><b>${fmtDur(t.tempo_s)}</b></div>
        <div class="kpi"><small>Recordes</small><b class="roxo">${t.recordes}</b></div></div>` : ''}
      <div class="cartao">${t.sessoes || jogo || tipo ? tabelaSessoes(d.sessoes, !jogo) : '<div class="vazio-grande"><h2>Nenhuma sessão ainda</h2><p class="fraco">Entre na pista com o Axtel aberto. As sessões aparecem aqui sozinhas.</p></div>'}</div>`;
  },
};

// ------------------------------------------------------------------ DETALHE DA SESSÃO
PAGINAS.sessao = {
  async html(r) {
    const id = Number(r.arg[0]);
    const d = await api('/api/sessao?id=' + id);
    if (d.erro) return `<div class="cartao"><h2>${esc(d.erro)}</h2><a class="btn" href="#/sessoes">← Voltar para Sessões</a></div>`;
    E.sessao = d;
    const s = d.sessao;
    if (!E.sel[id]) E.sel[id] = selecaoPadrao(d.voltas);
    const melhor = s.melhor_ms;
    const ehPb = melhor && d.pb_ms === melhor;
    return `<div class="linha" style="margin-bottom:10px">
        <span class="esp"></span>
        <a class="btn" ${d.mais_nova ? `href="#/sessao/${d.mais_nova}"` : 'aria-disabled="true" style="opacity:.4;pointer-events:none"'}>← Mais nova</a>
        <span class="fraco" style="font-size:12px">${d.posicao} de ${d.total}</span>
        <a class="btn" ${d.mais_antiga ? `href="#/sessao/${d.mais_antiga}"` : 'aria-disabled="true" style="opacity:.4;pointer-events:none"'}>Mais antiga →</a>
      </div>
      <h1>${esc(s.carro)} · ${esc(s.pista)}</h1>
      <p class="sub">${esc(s.jogo)} · ${esc(s.tipo)} · ${fmtDataLonga(s.inicio)} · ${fmtDur(s.tempo_s)} na pista ${s.aberta ? '<span class="selo ok">gravando agora</span>' : ''}</p>
      <div class="kpis">
        <div class="kpi"><small>Melhor volta</small><b class="${ehPb ? 'roxo' : ''}">${fmtVolta(melhor)}</b><span>${ehPb ? 'recorde pessoal' : d.pb_ms ? 'recorde: ' + fmtVolta(d.pb_ms) : ''}</span></div>
        <div class="kpi"><small>Média das válidas</small><b>${fmtVolta(d.media_ms)}</b><span>${d.desvio_ms != null ? 'variação ±' + (d.desvio_ms / 1000).toFixed(3) : ''}</span></div>
        <div class="kpi"><small>Volta ideal</small><b>${fmtVolta(d.ideal_ms)}</b><span>${d.ideal_ms && melhor ? 'soma das melhores parciais · ' + fmtDelta(d.ideal_ms - melhor) : 'soma das melhores parciais'}</span></div>
        <div class="kpi"><small>Voltas válidas</small><b>${s.validas}<span class="fraco" style="font-size:16px">/${s.voltas}</span></b><span>${km((s.distancia_m || 0) / 1000)}</span></div>
      </div>
      <div class="cartao"><div class="linha"><h2 style="margin:0">Setup usado</h2><span class="esp"></span>
        ${d.setups.length ? `<select class="campo" data-mudar="sessao-setup" data-sid="${s.id}" aria-label="Setup usado nesta sessão"><option value="">Não informado</option>${d.setups.map((x) => `<option value="${x.id}" ${s.setup_id === x.id ? 'selected' : ''}>${esc(x.nome)}</option>`).join('')}</select>`
          : '<span class="fraco" style="font-size:13px">Nenhum setup registrado para este carro e pista.</span>'}
        <a class="btn" href="#/setups?combo=${enc([s.jogo, s.carro, s.pista].join('|'))}">${d.setups.length ? 'Ver setups' : 'Registrar setup'}</a></div>
        <span id="setup-msg" class="fraco" style="font-size:12.5px"></span></div>
      <div class="cartao" id="cartao-voltas"></div>
      <div class="cartao"><div class="linha"><h2 style="margin:0">Exportar e organizar</h2><span class="esp"></span>
        <a class="btn" href="/api/sessao/csv?id=${s.id}">Baixar voltas (CSV para Excel)</a>
        <button class="btn perigo" data-acao="apagar" data-id="${s.id}">Apagar sessão</button></div>
        <div id="apagar-confirma"></div></div>`;
  },
  depois(r) { desenharVoltas(Number(r.arg[0])); },
};

function selecaoPadrao(voltas) {
  const val = voltas.filter((v) => v.valida);
  if (!val.length) return { ref: voltas.length ? voltas[0].id : null, cmp: [] };
  const melhor = val.reduce((a, b) => (b.tempo_ms < a.tempo_ms ? b : a));
  // REF = melhor volta; comparada = a última válida (ou a anterior, se a melhor for a última)
  const outras = val.filter((v) => v.id !== melhor.id);
  return { ref: melhor.id, cmp: outras.length ? [outras[outras.length - 1].id] : [] };
}
function alternarVolta(sid, vid) {
  const s = E.sel[sid];
  if (vid === s.ref) return;
  const i = s.cmp.indexOf(vid);
  if (i >= 0) s.cmp.splice(i, 1); else s.cmp.push(vid);
  desenharVoltas(sid);
}
function virarRef(sid, vid) {
  const s = E.sel[sid];
  s.ref = vid;
  s.cmp = s.cmp.filter((x) => x !== vid);
  desenharVoltas(sid);
}

function desenharVoltas(sid) {
  const cartao = $('#cartao-voltas');
  const d = E.sessao;
  if (!cartao || !d || d.sessao.id !== sid) return;
  const vs = d.voltas;
  const sel = E.sel[sid];
  const porId = Object.fromEntries(vs.map((v) => [v.id, v]));
  sel.cmp = sel.cmp.filter((x) => porId[x]).sort((x, y) => porId[x].numero - porId[y].numero);
  const val = vs.filter((v) => v.valida);
  const melhor = val.length ? Math.min(...val.map((v) => v.tempo_ms)) : null;
  const melhorP = ['p1', 'p2', 'p3'].map((k) => { const xs = val.map((v) => v[k]).filter(Boolean); return xs.length ? Math.min(...xs) : null; });
  const tempos = vs.map((v) => v.tempo_ms);
  const base = melhor || Math.min(...tempos);
  const teto = Math.min(Math.max(...tempos), base * 1.12);
  const piso = base * 0.985;
  const altura = (t) => (t < piso ? 100 : Math.max(6, Math.min(100, ((Math.min(t, teto) - piso) / (teto - piso || 1)) * 94 + 6)));
  const papel = (id) => (sel.ref === id ? 'ref' : sel.cmp.includes(id) ? 'vs' : '');
  const A = porId[sel.ref], Bs = sel.cmp.map((x) => porId[x]);
  const cor = (x) => (x > 5 ? 'vermelho' : x < -5 ? 'verde' : 'fraco');
  let cmp = '';
  if (A && Bs.length) {
    const med = (f) => Bs.reduce((s, b) => s + f(b), 0) / Bs.length;
    const dt = med((b) => b.tempo_ms - A.tempo_ms);
    const partes = ['p1', 'p2', 'p3'].map((k, i) => (A[k] && Bs.every((b) => b[k]) ? { n: i + 1, d: med((b) => b[k] - A[k]) } : null)).filter(Boolean);
    const pior = partes.length ? partes.reduce((x, y) => (y.d > x.d ? y : x)) : null;
    cmp = `<div class="cmp">
      <div class="linha"><span><span class="tag-sel ref" style="margin:0 6px 0 0">REF</span>Volta ${A.numero} <span class="mono">${fmtVolta(A.tempo_ms)}</span></span>
        <span class="fraco">contra</span><span>${Bs.length === 1 ? `volta ${Bs[0].numero}` : plural(Bs.length, 'volta', 'voltas')}</span>
        <span class="esp"></span><span class="fraco" style="font-size:12.5px">${Bs.length > 1 ? 'diferença média' : 'diferença'}</span><b class="${cor(dt)}">${fmtDelta(Math.round(dt))}</b></div>
      ${partes.length ? `<div class="linha" style="margin-top:8px;gap:18px">${partes.map((p) => `<span>Parcial ${p.n}${Bs.length > 1 ? ' (média)' : ''}: <b class="mono ${cor(p.d)}" style="font-size:14px">${fmtDelta(Math.round(p.d))}</b></span>`).join('')}</div>
        ${pior && pior.d > 5 ? `<p class="fraco" style="margin:6px 0 0">${Bs.length > 1 ? 'Em média, as voltas marcadas perdem' : `A volta ${Bs[0].numero} perdeu`} mais tempo na parcial ${pior.n} (${fmtDelta(Math.round(pior.d))}).</p>` : ''}` : ''}
      <div class="rolar" style="margin-top:10px"><table><caption class="fraco" style="text-align:left;font-size:12.5px;padding-bottom:4px">Cada volta marcada contra a REF. Para tirar uma volta, desmarque em Comparar.</caption>
        <thead><tr><th>Volta</th><th>Tempo</th><th>Diferença</th><th>Parcial 1</th><th>Parcial 2</th><th>Parcial 3</th><th>Onde mais perdeu</th><th></th></tr></thead><tbody>
        ${Bs.map((b) => {
          const x = ['p1', 'p2', 'p3'].map((k) => (A[k] && b[k] ? b[k] - A[k] : null));
          const k = x.reduce((m, v, i) => (v != null && (m < 0 || v > x[m]) ? i : m), -1);
          return `<tr><td class="mono"><span class="tag-sel vs" style="margin:0 6px 0 0">VS</span>${b.numero}</td><td class="mono">${fmtVolta(b.tempo_ms)}</td>
            <td class="mono ${cor(b.tempo_ms - A.tempo_ms)}"><b>${fmtDelta(b.tempo_ms - A.tempo_ms)}</b></td>
            ${x.map((v) => `<td class="mono ${v == null ? 'fraco' : cor(v)}">${v == null ? '—' : fmtDelta(v)}</td>`).join('')}
            <td>${k >= 0 && x[k] > 5 ? `Parcial ${k + 1} (${fmtDelta(x[k])})` : '<span class="fraco">não perdeu</span>'}</td>
            <td><a class="btn" style="padding:3px 10px" href="#/comparar/${A.id},${b.id}">Só esta</a></td></tr>`;
        }).join('')}</tbody></table></div>
      <div class="linha" style="margin-top:10px"><a class="btn pri" href="#/comparar/${[A.id].concat(Bs.map((b) => b.id)).slice(0, 10).join(',')}">Ver gráficos e traçado ${Bs.length > 1 ? 'das ' + Math.min(Bs.length + 1, 10) + ' voltas' : 'das duas voltas'} →</a>${Bs.length > 9 ? '<span class="fraco" style="font-size:12.5px">o gráfico mostra até 10 voltas</span>' : ''}</div>
    </div>`;
  } else {
    cmp = `<div class="cmp fraco">Escolha a referência na coluna REF e marque quantas voltas quiser em Comparar (ou clique nas barras).</div>`;
  }
  cartao.innerHTML = `<div class="linha"><h2 style="margin:0">Voltas</h2><span class="esp"></span>
      <button class="btn" data-acao="sel-melhores" data-sid="${sid}">Melhor + última</button>
      <button class="btn" data-acao="sel-todas" data-sid="${sid}">Todas as válidas</button>
      <button class="btn" data-acao="sel-limpar" data-sid="${sid}">Limpar comparadas</button></div>
    <div class="grafico-voltas" role="group" aria-label="Tempo de cada volta">
      ${vs.map((v) => `<button data-acao="volta" data-sid="${sid}" data-vid="${v.id}" class="${v.valida ? 'valida' : ''} ${v.tempo_ms === melhor && v.valida ? 'melhor' : ''} ${papel(v.id)}"
        style="height:${altura(v.tempo_ms)}%" title="Volta ${v.numero}: ${fmtVolta(v.tempo_ms)}${v.valida ? '' : ' (inválida)'}" aria-label="Volta ${v.numero}, ${fmtVolta(v.tempo_ms)}: marcar ou desmarcar para comparar"></button>`).join('')}
    </div>
    <div class="legenda"><span><i style="background:#56606E"></i>válida</span><span><i style="background:#3A4350"></i>inválida</span><span><i style="background:var(--roxo)"></i>melhor</span><span><i style="background:var(--destaque)"></i>REF</span><span><i style="background:var(--azul)"></i>comparadas</span><span>barras mais baixas = voltas mais rápidas</span></div>
    ${cmp}
    <div class="rolar"><table><thead><tr><th>REF</th><th>Comparar</th><th>Volta</th><th>Tempo</th><th>Δ melhor</th><th>Parcial 1</th><th>Parcial 2</th><th>Parcial 3</th><th>Vel. máx</th><th>Combustível</th><th>Situação</th></tr></thead><tbody>
    ${vs.map((v) => `<tr class="${papel(v.id) ? 'sel' : ''}">
      <td><label class="linha" style="gap:6px;cursor:pointer"><input type="radio" name="ref-${sid}" class="marca" data-mudar="ref" data-sid="${sid}" data-vid="${v.id}" ${sel.ref === v.id ? 'checked' : ''} aria-label="Usar a volta ${v.numero} como referência">${sel.ref === v.id ? '<span class="tag-sel ref">REF</span>' : ''}</label></td>
      <td><input type="checkbox" class="marca" data-mudar="volta" data-sid="${sid}" data-vid="${v.id}" ${sel.cmp.includes(v.id) ? 'checked' : ''} ${sel.ref === v.id ? 'disabled' : ''} aria-label="Comparar a volta ${v.numero} com a referência"></td>
      <td>${v.numero}</td>
      <td class="mono ${v.valida && v.tempo_ms === melhor ? 'roxo' : ''} ${v.valida ? '' : 'fraco'}">${fmtVolta(v.tempo_ms)}</td>
      <td class="mono fraco">${v.valida && melhor ? (v.tempo_ms === melhor ? '—' : fmtDelta(v.tempo_ms - melhor)) : ''}</td>
      ${['p1', 'p2', 'p3'].map((k, i) => `<td class="mono ${v.valida && v[k] && v[k] === melhorP[i] ? 'roxo' : ''}">${fmtParcial(v[k])}</td>`).join('')}
      <td class="mono">${v.vel_max ? Math.round(v.vel_max) + ' km/h' : '—'}</td>
      <td class="mono">${v.combustivel != null ? v.combustivel.toFixed(2).replace('.', ',') + ' L' : '—'}</td>
      <td>${v.valida ? '<span class="selo ok">válida</span>' : `<span class="selo ruim" title="${esc(v.motivo || '')}">${esc(v.motivo || 'inválida')}</span>`}</td>
    </tr>`).join('')}
    </tbody></table></div>
    <p class="fraco" style="font-size:12px;margin:10px 0 0">Parciais: a volta dividida em três partes iguais. Em roxo, o melhor de cada coluna. A REF não pode ser comparada com ela mesma.</p>`;
}

// ------------------------------------------------------------------ COMPARAR (várias voltas, cores, mostrar/ocultar)
const CORES_VOLTAS = ['#F2A93B', '#4CC3FF', '#F472B6', '#4ADE80', '#C084FC', '#FACC15', '#F87171', '#2DD4BF', '#E9ECEF', '#FB923C'];
const INFOS_CMP = [['mapa', 'Traçado e replay'], ['delta', 'Diferença de tempo'], ['vel', 'Velocidade'], ['acel', 'Acelerador'], ['freio', 'Freio'], ['marcha', 'Marcha']];
function cmpInfo() {
  if (!E.cmpInfo) E.cmpInfo = recuperar('axtel.comparar.info', { mapa: true, delta: true, vel: true, acel: true, freio: true, marcha: true });
  return E.cmpInfo;
}
PAGINAS.comparar = {
  async html(r) {
    const ids = r.arg.join(',').split(',').map(Number).filter(Boolean);
    if (!ids.length) return `<div class="cartao"><h2>Nenhuma volta escolhida</h2><a class="btn" href="#/sessoes">← Sessões</a></div>`;
    const voltas = await Promise.all(ids.slice(0, 10).map((id) => api('/api/volta?id=' + id)));
    const ok = voltas.filter((v) => !v.erro);
    if (!ok.length) return `<div class="cartao"><h2>Volta não encontrada</h2><a class="btn" href="#/sessoes">← Sessões</a></div>`;
    const sessao = await api('/api/sessao?id=' + ok[0].sessao_id);
    ok.forEach((v, i) => { v.cor = CORES_VOLTAS[i % CORES_VOLTAS.length]; });
    const A = ok[0], info = cmpInfo();
    E.cmp = { voltas: ok, ref: A };
    if (!E.cmpOcultas || E.cmpChave !== ids.join(',')) { E.cmpOcultas = []; E.cmpChave = ids.join(','); }
    const vis = ok.filter((v) => v === A || !E.cmpOcultas.includes(v.id));
    E.cmp.vis = vis;
    const Bs = vis.filter((v) => v !== A);
    const temMapa = vis.some((v) => v.amostras.some((p) => p[6] || p[7]));
    const nome = (v) => `Volta ${v.numero}${v.sessao_id !== A.sessao_id ? ' (' + fmtData(v.inicio) + ')' : ''}`;
    const dif = (v) => v.tempo_ms - A.tempo_ms;
    const cor = (x) => (x > 5 ? 'vermelho' : x < -5 ? 'verde' : 'fraco');
    const parciais = (v) => ['p1', 'p2', 'p3'].map((k) => (A[k] && v[k] ? v[k] - A[k] : null));
    const media = Bs.length ? Bs.reduce((s, v) => s + dif(v), 0) / Bs.length : null;
    const perto = Bs.slice().sort((x, y) => Math.abs(dif(x)) - Math.abs(dif(y)))[0];
    const soma = [0, 1, 2].map((i) => Bs.reduce((s, v) => s + (parciais(v)[i] || 0), 0));
    const piorP = Bs.length ? soma.indexOf(Math.max(...soma)) : -1;
    const outras = sessao.voltas ? sessao.voltas.filter((x) => !ids.includes(x.id)) : [];
    const linhaCor = (v, w = 22) => `<span style="display:inline-block;width:${w}px;height:0;border-top:3px solid ${v.cor};vertical-align:middle"></span>`;
    const deltas = Bs.map((v) => v.amostras.map((p) => [p[0], p[1] - tempoEm(A.amostras, p[0])]).filter((p) => p[0] > 0.005 && p[0] < 0.995));
    const serie = (f, larg) => vis.map((v) => ({ pts: v.amostras.map((p) => [p[0], f(p)]), cor: v.cor, largura: v === A ? 2.4 : (larg || 1.6) }));
    const graf = {
      delta: () => `<div class="cartao"><h2>Diferença ao longo da volta (segundos)</h2><p class="fraco" style="margin:-6px 0 10px;font-size:12px">Acima de zero: aquela volta está atrás da REF naquele ponto. Onde a linha sobe, perdeu tempo.${Object.keys(escalaDelta(deltas)).length ? ' Escala limitada a ±5 s: alguma volta marcada está muito longe da REF (por exemplo, a volta de saída).' : ''}</p>
        ${Bs.length ? grafico({ series: [{ pts: [[0, 0], [1, 0]], cor: A.cor, largura: 2 }].concat(Bs.map((v, i) => ({ pts: deltas[i], cor: v.cor }))), zero: true, ...escalaDelta(deltas), altura: 160, fmtY: (y) => (y / 1000).toFixed(2), idCursor: 'cur-delta', rotulosX: ['largada', '25%', '50%', '75%', 'chegada'] }) : '<p class="fraco">Marque pelo menos uma volta além da REF.</p>'}</div>`,
      vel: () => `<div class="cartao"><h2>Velocidade (km/h)</h2>${grafico({ series: serie((p) => p[2]), altura: 200, fmtY: (y) => Math.round(y), idCursor: 'cur-vel', rotulosX: ['largada', '25%', '50%', '75%', 'chegada'] })}</div>`,
      acel: () => `<div class="cartao"><h2>Acelerador (%)</h2>${grafico({ series: serie((p) => p[3] * 100, 1.4), ymin: 0, ymax: 100, altura: 110, fmtY: (y) => Math.round(y), idCursor: 'cur-acel' })}</div>`,
      freio: () => `<div class="cartao"><h2>Freio (%)</h2>${grafico({ series: serie((p) => p[4] * 100, 1.4), ymin: 0, ymax: 100, altura: 110, fmtY: (y) => Math.round(y), idCursor: 'cur-freio' })}</div>`,
      marcha: () => `<div class="cartao"><h2>Marcha</h2>${grafico({ series: serie((p) => p[5], 1.4), altura: 100, fmtY: (y) => Math.round(y), idCursor: 'cur-marcha' })}</div>`,
    };
    return `<h1>Comparar voltas</h1>
      <p class="sub">${esc(A.carro)} · ${esc(A.pista)} · ${esc(A.jogo)}. Cada volta tem uma cor; a primeira é a referência (REF).</p>
      <div class="cartao"><div class="linha"><h2 style="margin:0">Voltas no gráfico</h2><span class="esp"></span>
          <button class="btn" data-acao="cmp-todas">Mostrar todas</button><button class="btn" data-acao="cmp-nenhuma">Ocultar todas, menos a REF</button></div>
        <div class="rolar" style="margin-top:8px"><table><thead><tr><th>Mostrar</th><th>Cor</th><th>Volta</th><th>Tempo</th><th>Diferença para a REF</th><th>Parcial 1</th><th>Parcial 2</th><th>Parcial 3</th><th>REF</th><th></th></tr></thead><tbody>
        ${ok.map((v) => { const x = parciais(v), ehRef = v === A, mostra = vis.includes(v); return `<tr class="${ehRef ? 'sel' : ''}">
          <td><input type="checkbox" class="marca" data-mudar="cmp-mostrar" data-id="${v.id}" ${mostra ? 'checked' : ''} ${ehRef ? 'disabled' : ''} aria-label="Mostrar ${nome(v)} no gráfico"></td>
          <td>${linhaCor(v, 28)}</td><td><b>${nome(v)}</b> ${v.valida ? '' : '<span class="selo ruim">inválida</span>'}</td><td class="mono">${fmtVolta(v.tempo_ms)}</td>
          <td class="mono ${ehRef ? 'amarelo' : cor(dif(v))}"><b>${ehRef ? 'referência' : fmtDelta(dif(v))}</b></td>
          ${x.map((d) => `<td class="mono ${ehRef || d == null ? 'fraco' : cor(d)}">${ehRef ? '—' : d == null ? '—' : fmtDelta(d)}</td>`).join('')}
          <td>${ehRef ? '<span class="tag-sel ref">REF</span>' : `<button class="btn" style="padding:3px 10px" data-acao="cmp-ref" data-id="${v.id}">Usar como REF</button>`}</td>
          <td>${ehRef ? '' : `<button class="btn" style="padding:3px 10px" data-acao="cmp-tirar" data-id="${v.id}" aria-label="Tirar ${nome(v)} da comparação">Tirar</button>`}</td></tr>`; }).join('')}
        </tbody></table></div>
        ${outras.length && ok.length < 10 ? `<div class="linha" style="margin-top:10px"><label class="fraco" for="cmp-add" style="font-size:13px">Adicionar volta desta sessão</label>
          <select class="campo" id="cmp-add" data-mudar="cmp-add"><option value="">Escolha…</option>${outras.map((x) => `<option value="${x.id}">Volta ${x.numero} · ${fmtVolta(x.tempo_ms)}${x.valida ? '' : ' (inválida)'}</option>`).join('')}</select></div>` : ''}
      </div>
      <div class="kpis">
        <div class="kpi" style="box-shadow:inset 3px 0 0 ${A.cor}"><small>Referência</small><b>${fmtVolta(A.tempo_ms)}</b><span>${nome(A)}</span></div>
        <div class="kpi"><small>Voltas comparadas</small><b>${Bs.length}</b><span>${Bs.length ? Bs.map((v) => 'volta ' + v.numero).join(', ') : 'nenhuma visível'}</span></div>
        <div class="kpi"><small>${Bs.length > 1 ? 'Diferença média' : 'Diferença'}</small><b class="${media == null ? 'fraco' : cor(media)}">${media == null ? '—' : fmtDelta(Math.round(media))}</b><span>${perto ? 'mais perto da REF: volta ' + perto.numero : ''}</span></div>
        <div class="kpi"><small>Parcial que mais custa</small><b class="vermelho">${piorP >= 0 && soma[piorP] > 5 ? 'Parcial ' + (piorP + 1) : '—'}</b><span>${piorP >= 0 && soma[piorP] > 5 ? 'média de ' + fmtDelta(Math.round(soma[piorP] / Bs.length)) + ' por volta' : 'nenhuma parcial perde tempo'}</span></div>
      </div>
      <div class="cartao"><div class="linha" style="gap:8px"><b style="margin-right:4px">Mostrar no gráfico:</b>
        ${INFOS_CMP.map(([k, n]) => `<button class="btn ${info[k] ? 'pri' : ''}" style="padding:4px 12px;font-size:13px" data-acao="cmp-info" data-k="${k}" aria-pressed="${!!info[k]}">${info[k] ? '✓' : '+'} ${n}</button>`).join('')}</div>
        <div class="legenda" style="margin-top:10px">${vis.map((v) => `<span>${linhaCor(v)} ${nome(v)}${v === A ? ' (REF)' : ''}</span>`).join('')}</div></div>
      ${info.mapa ? (temMapa ? `<div class="cartao"><div class="linha"><h2 style="margin:0">Traçado e replay</h2><span class="esp"></span>
          <button class="btn pri" data-acao="replay-play" id="replay-play">▶ Reproduzir</button>
          <div class="alternar" id="replay-vel">${[0.5, 1, 2, 4].map((x) => `<button data-acao="replay-vel" data-v="${x}" class="${x === 1 ? 'on' : ''}">${String(x).replace('.', ',')}×</button>`).join('')}</div></div>
        <div class="grade g2" style="margin-top:12px;align-items:start">
          <div>${mapaSvg(vis)}</div>
          <div><div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))"><div class="kpi"><small>Tempo do replay</small><b id="rp-t">0:00.000</b></div></div>
            <div id="rp-voltas"></div>
            <label class="fraco" for="replay-pos" style="font-size:12px">Arraste para ir a qualquer ponto da volta</label>
            <input type="range" id="replay-pos" min="0" max="1000" value="0" data-mudar="replay"></div>
        </div></div>` : '<div class="aviso">Este jogo não mandou a posição do carro na pista, então o traçado não está disponível para estas voltas.</div>') : ''}
      ${['delta', 'vel'].filter((k) => info[k]).map((k) => graf[k]()).join('')}
      ${['acel', 'freio'].some((k) => info[k]) ? `<div class="grade g2">${['acel', 'freio'].filter((k) => info[k]).map((k) => graf[k]()).join('')}</div>` : ''}
      ${info.marcha ? graf.marcha() : ''}
      ${!INFOS_CMP.some(([k]) => info[k]) ? '<div class="cartao fraco">Todas as informações estão ocultas. Ligue alguma acima.</div>' : ''}`;
  },
  depois() {
    const R = { t: 0, vel: 1, tocando: false, ult: 0, raf: 0 };
    E.replay = R;
    atualizarReplay();
    E.pararPagina = () => { cancelAnimationFrame(R.raf); E.replay = null; };
  },
};
// escala do gráfico de diferença: até ±5 s, para uma volta incompleta não achatar as outras
function escalaDelta(deltas) {
  const m = Math.max(300, ...deltas.flat().map((p) => Math.abs(p[1])));
  return m > 5000 ? { ymin: -5000, ymax: 5000 } : {};
}
function irComparar(ids) { location.hash = '#/comparar/' + ids.join(','); }

// tempo (ms) em que uma volta passou por uma posição (0..1)
function tempoEm(amostras, npos) {
  if (!amostras.length) return 0;
  let lo = 0, hi = amostras.length - 1;
  if (npos <= amostras[0][0]) return amostras[0][1];
  if (npos >= amostras[hi][0]) return amostras[hi][1];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (amostras[m][0] < npos) lo = m; else hi = m; }
  const a = amostras[lo], b = amostras[hi];
  const f = b[0] === a[0] ? 0 : (npos - a[0]) / (b[0] - a[0]);
  return a[1] + (b[1] - a[1]) * f;
}
// amostra interpolada num instante (ms)
function pontoEm(amostras, t) {
  if (!amostras.length) return null;
  let lo = 0, hi = amostras.length - 1;
  if (t <= amostras[0][1]) return amostras[0];
  if (t >= amostras[hi][1]) return amostras[hi];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (amostras[m][1] < t) lo = m; else hi = m; }
  const a = amostras[lo], b = amostras[hi];
  const f = b[1] === a[1] ? 0 : (t - a[1]) / (b[1] - a[1]);
  return a.map((v, i) => (i === 5 ? (f < 0.5 ? a[5] : b[5]) : v + (b[i] - v) * f));
}

let MAPA = null;
function mapaSvg(voltas) {
  const pts = voltas.flatMap((v) => v.amostras).filter((p) => p[6] || p[7]);
  const xs = pts.map((p) => p[6]), zs = pts.map((p) => p[7]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
  const larg = x1 - x0 || 1, alt = z1 - z0 || 1;
  const W = 600, H = Math.max(260, Math.min(600, (W * alt) / larg)), m = 18;
  const k = Math.min((W - 2 * m) / larg, (H - 2 * m) / alt);
  const ox = (W - larg * k) / 2, oz = (H - alt * k) / 2;
  const P = (p) => [ox + (p[6] - x0) * k, oz + (z1 - p[7]) * k];
  MAPA = P;
  const path = (am) => am.filter((p) => p[6] || p[7]).map((p, i) => (i ? 'L' : 'M') + P(p).map((v) => v.toFixed(1)).join(' ')).join('');
  const ref = voltas[0];
  const inicio = ref.amostras.find((p) => p[6] || p[7]);
  const [sx, sy] = inicio ? P(inicio) : [0, 0];
  return `<svg class="mapa" viewBox="0 0 ${W} ${H}" role="img" aria-label="Traçado das voltas escolhidas">
    <path d="${path(ref.amostras)}" fill="none" stroke="#2A323D" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>
    ${voltas.map((v, i) => `<path d="${path(v.amostras)}" fill="none" stroke="${v.cor}" stroke-width="${i ? 1.6 : 2.4}" stroke-linejoin="round" ${i ? 'stroke-dasharray="5 3"' : ''}/>`).join('')}
    <rect x="${sx - 2}" y="${sy - 8}" width="4" height="16" fill="#fff"/>
    ${voltas.slice().reverse().map((v) => `<circle class="pin" data-id="${v.id}" r="7" fill="${v.cor}" stroke="#0D1015" stroke-width="2" cx="-20" cy="-20"/>`).join('')}
    <text x="${sx > W - 90 ? sx - 8 : sx + 8}" y="${sy - 12}" text-anchor="${sx > W - 90 ? 'end' : 'start'}">largada</text>
  </svg>`;
}
function tmaxCmp() { return Math.max(...E.cmp.vis.map((v) => v.tempo_ms)); }
function atualizarReplay() {
  const R = E.replay, c = E.cmp;
  if (!R || !c || !c.vis) return;
  const A = c.ref, pa = pontoEm(A.amostras, R.t);
  const set = (id, v) => { const el = $('#' + id); if (el) el.textContent = v; };
  set('rp-t', fmtVolta(R.t));
  const linhas = [];
  c.vis.forEach((v) => {
    const p = pontoEm(v.amostras, R.t);
    const pin = $(`circle.pin[data-id="${v.id}"]`);
    if (pin && p && MAPA) { const [x, y] = MAPA(p); pin.setAttribute('cx', x); pin.setAttribute('cy', y); }
    if (p && pa) {
      const d = v === A ? null : Math.round(tempoEm(v.amostras, pa[0]) - tempoEm(A.amostras, pa[0]));
      linhas.push(`<div class="linha" style="font-size:13px;min-height:28px"><span style="display:inline-block;width:18px;height:0;border-top:3px solid ${v.cor}"></span>
        <b style="width:76px">Volta ${v.numero}</b><span class="mono" style="width:70px">${Math.round(p[2])} km/h</span><span class="fraco" style="width:62px">marcha ${p[5]}</span>
        <span class="mono ${d == null ? 'amarelo' : d > 5 ? 'vermelho' : d < -5 ? 'verde' : 'fraco'}">${d == null ? 'REF' : fmtDelta(d)}</span></div>`);
    }
  });
  const box = $('#rp-voltas'); if (box) box.innerHTML = linhas.join('');
  if (pa) ['cur-vel', 'cur-delta', 'cur-acel', 'cur-freio', 'cur-marcha'].forEach((id) => { const l = $('#' + id); if (l) { l.setAttribute('x1', pa[0] * 1000); l.setAttribute('x2', pa[0] * 1000); } });
  const tmax = tmaxCmp();
  const pos = $('#replay-pos');
  if (pos && document.activeElement !== pos) pos.value = Math.round((R.t / tmax) * 1000);
  const btn = $('#replay-play');
  if (btn) btn.textContent = R.tocando ? '❚❚ Pausar' : R.t >= tmax ? '↺ Reproduzir de novo' : '▶ Reproduzir';
}
function quadroReplay(agora) {
  const R = E.replay;
  if (!R || !R.tocando) return;
  const tmax = tmaxCmp();
  R.t = Math.min(tmax, R.t + (agora - R.ult) * R.vel);
  R.ult = agora;
  if (R.t >= tmax) R.tocando = false;
  atualizarReplay();
  if (R.tocando) R.raf = requestAnimationFrame(quadroReplay);
}

// ------------------------------------------------------------------ AO VIVO
PAGINAS.aovivo = {
  async html() {
    const st = E.status || (await api('/api/status').catch(() => null));
    const endereco = st ? `http://${st.ip}:${st.porta}` : '';
    const c = SP.cfg;
    return `<div class="linha so-painel" style="align-items:flex-end;margin-bottom:12px"><div style="flex:1 1 320px"><h1>Ao vivo</h1>
        <p class="sub" style="margin:0">O que está acontecendo agora na pista, atualizado 4 vezes por segundo.</p></div>
        <button class="btn" data-acao="vivo-tela-cheia">Tela cheia</button>
        <button class="btn pri" data-acao="vivo-janela">Abrir em janela separada</button></div>
      <div class="linha so-janela" style="margin-bottom:10px"><b style="letter-spacing:.08em">AXTEL · AO VIVO</b><span class="esp"></span>
        <button class="btn" data-acao="vivo-tela-cheia">Tela cheia</button></div>
      <div id="vivo"></div>
      <div class="grade g2 so-painel">
        <div class="cartao"><div class="linha"><h2 style="margin:0">Spotter</h2><span class="esp"></span>
          <span class="selo ${c && c.ligado ? 'ok' : ''}">${c && c.ligado ? 'ligado' : 'desligado'}</span></div>
          <p class="fraco" style="margin:8px 0 6px">Último aviso:</p><p id="sp-ultimo" style="margin:0 0 4px">${SP.ultimo ? '“' + esc(SP.ultimo) + '”' : '—'}</p>
          <p class="fraco" id="sp-voz-usada" style="margin:0 0 12px;font-size:12.5px"></p>
          <div class="linha"><button class="btn" data-acao="sp-repetir">Repetir último aviso</button><a class="btn pri" href="#/spotter">Abrir o Spotter</a></div>
        </div>
        <div class="cartao"><h2>Ver no celular</h2>
          <p style="margin:0 0 6px">Com o celular no mesmo Wi-Fi do PC, abra no navegador do celular:</p>
          <p class="mono" style="font-size:20px;margin:0 0 8px;color:var(--destaque)">${esc(endereco)}</p>
          <p class="fraco" style="margin:0;font-size:12.5px">Se não abrir: na primeira vez o Windows pergunta se o Python pode usar a rede. Marque "Redes privadas" e clique em Permitir.</p></div>
      </div>`;
  },
  depois() {
    let vivo = true;
    const ciclo = async () => {
      if (!vivo) return;
      try { desenharVivo(await api('/api/aovivo')); } catch (e) { desenharVivo(null); }
      if (vivo) E.timerVivo = setTimeout(ciclo, 250);
    };
    ciclo();
    E.pararPagina = () => { vivo = false; clearTimeout(E.timerVivo); };
  },
};

// ------------------------------------------------------------------ SPOTTER
PAGINAS.spotter = {
  async html() {
    if (!SP.cfg) await carregarSpotter();
    const [ve] = await Promise.all([api('/api/voz/estado').catch(() => ({ chave: false }))]);
    const c = SP.cfg, l = spLingua();
    const op = (grupo, valor, nome, desc, atual) => `<button class="op ${atual === valor ? 'on' : ''}" data-acao="sp-op" data-campo="${grupo}" data-v="${valor}" aria-pressed="${atual === valor}"><b>${nome}</b><small>${desc}</small></button>`;
    const chk = (campo, txt) => `<label class="linha" style="min-height:40px"><input type="checkbox" class="marca" data-mudar="sp-chk" data-campo="${campo}" ${c[campo] ? 'checked' : ''}> ${txt}</label>`;
    const vozes = c.vozes || {};
    const navVozes = ('speechSynthesis' in window) ? speechSynthesis.getVoices().filter((v) => v.lang && v.lang.toLowerCase().startsWith(l)) : [];
    const atualNav = melhorVozNavegador(l);
    return `<div class="linha" style="align-items:flex-end;margin-bottom:16px"><div style="flex:1 1 380px"><h1>Spotter</h1>
        <p class="sub" style="margin:0">Seu engenheiro de rádio: fala o tempo das voltas, avisa recordes, voltas inválidas, combustível e boxes.</p></div>
        <button class="btn ${c.ligado ? 'pri' : ''}" style="min-height:48px;padding:0 20px;font-size:16px" data-acao="sp-ligar">${c.ligado ? '● Spotter ligado' : '○ Spotter desligado'}</button></div>
      <div class="cartao" style="border-color:#5A4520;background:#1E1A12">
        <div class="linha"><b style="color:#E3C38C">Último aviso:</b><span id="sp-ultimo" style="flex:1 1 260px">${SP.ultimo ? '“' + esc(SP.ultimo) + '”' : 'nenhum ainda'}</span>
          <button class="btn" data-acao="sp-repetir">Repetir último aviso</button>
          <button class="btn" data-acao="sp-silenciar">${SP.silencioVolta !== null ? 'Voltar a falar' : 'Silenciar por 1 volta'}</button></div>
        <p class="fraco" id="sp-voz-usada" style="margin:8px 0 0;font-size:12.5px"></p>
      </div>
      <div class="grade g2">
        <div class="cartao"><h2>Como ele fala</h2>
          <p class="fraco" style="margin:0 0 6px;font-size:13px">Quanto falar</p>
          <div class="grupo-op">${op('modo', 'silencioso', 'Só o essencial', 'Recordes, inválidas e combustível', c.modo)}${op('modo', 'normal', 'Normal', 'Tempo de cada volta e avisos úteis', c.modo)}${op('modo', 'falador', 'Tudo', 'Inclui as parciais', c.modo)}</div>
          <label class="fraco" style="display:block;margin-top:14px;font-size:13px">Volume · <span id="sp-vol-txt">${c.volume}%</span>
            <input type="range" min="0" max="100" step="5" value="${c.volume}" data-mudar="sp-num" data-campo="volume"></label>
          <label class="fraco" style="display:block;margin-top:10px;font-size:13px">Velocidade da fala · <span id="sp-rit-txt">${(c.ritmo / 100).toFixed(2).replace('.', ',')}×</span>
            <input type="range" min="80" max="140" step="5" value="${c.ritmo}" data-mudar="sp-num" data-campo="ritmo"></label>
        </div>
        <div class="cartao"><h2>Voz e idioma</h2>
          <label class="fraco" style="font-size:13px">Idioma do spotter</label>
          <select class="campo-largo" data-mudar="sp-sel" data-campo="lingua" style="margin:4px 0 12px">
            <option value="auto" ${c.lingua === 'auto' ? 'selected' : ''}>Automático · igual ao navegador (${LINGUAS[linguaDetectada()]})</option>
            ${Object.entries(LINGUAS).map(([k, v]) => `<option value="${k}" ${c.lingua === k ? 'selected' : ''}>${v}</option>`).join('')}</select>
          <div class="aviso-item">
            <div class="linha"><b>ElevenLabs</b><span class="esp"></span><span class="selo ${ve.chave ? 'ok' : 'ruim'}">${ve.chave ? 'chave encontrada' : 'sem chave neste PC'}</span></div>
            <span class="fraco" style="font-size:12.5px">${ve.chave ? `${plural(ve.guardadas || 0, 'frase guardada', 'frases guardadas')} no PC (tocam de graça).` : 'Sem a chave, o spotter usa a voz do navegador. O passo a passo está no guia.'}${ve.ultimo_erro ? ' Último erro: ' + esc(ve.ultimo_erro) : ''}</span>
            ${['pt', 'en', 'es'].map((k) => `<div class="linha" style="gap:8px"><span style="width:84px" class="fraco">${LINGUAS[k].split(' ')[0]}</span>
              <input class="campo" style="flex:1 1 110px;min-width:0" value="${esc((vozes[k] || {}).nome || '')}" placeholder="ainda não escolhida" data-mudar="sp-voz" data-l="${k}" data-campo="nome" aria-label="Nome da voz em ${LINGUAS[k]}">
              <input class="campo mono" style="flex:2 1 170px;min-width:0;font-size:12.5px" value="${esc((vozes[k] || {}).id || '')}" placeholder="cole o ID da voz aqui" data-mudar="sp-voz" data-l="${k}" data-campo="id" aria-label="ID da voz em ${LINGUAS[k]}"></div>`).join('')}
            <span class="fraco" style="font-size:12.5px">Idioma sem voz escolhida usa a voz do navegador.</span>
          </div>
          <label class="fraco" style="display:block;margin-top:12px;font-size:13px">Voz do navegador (quando não houver ElevenLabs)</label>
          <select class="campo-largo" data-mudar="sp-voz-nav" style="margin-top:4px">${navVozes.length ? navVozes.map((v) => `<option ${atualNav && atualNav.name === v.name ? 'selected' : ''}>${esc(v.name)}</option>`).join('') : '<option>Voz padrão</option>'}</select>
          <button class="btn pri" data-acao="sp-testar">Testar voz</button>
        </div>
      </div>
      <div class="cartao"><div class="linha"><h2 style="margin:0">O que ele avisa</h2><span class="esp"></span><span class="fraco">${AVISOS.filter((a) => spAvisoLigado(a[0])).length} de ${AVISOS.length} ligados</span></div>
        <div class="grade-avisos" style="margin-top:12px">${AVISOS.map((a) => {
          const letra = c.modo === 'silencioso' ? 's' : c.modo === 'falador' ? 'f' : 'n';
          const porModo = a[3].includes(letra), on = spAvisoLigado(a[0]);
          return `<div class="aviso-item" style="${on ? '' : 'opacity:.65'}">
            <label class="linha" style="cursor:pointer"><input type="checkbox" class="marca" data-mudar="sp-aviso" data-id="${a[0]}" ${on ? 'checked' : ''}><b>${a[1]}</b><span class="esp"></span>${a[4] ? `<span class="selo pb">${a[4]}</span>` : ''}</label>
            <span class="fraco" style="font-size:12.5px">${a[2]}${porModo ? '' : ' Desligado neste modo: marque para passar ao modo Tudo.'}</span>
            <div class="linha"><button class="btn" style="padding:3px 10px" data-acao="sp-exemplo" data-id="${a[0]}" aria-label="Ouvir exemplo">▶</button><i class="fraco" style="font-size:12.5px">“${esc(fraseExemplo(a[0], l))}”</i></div></div>`;
        }).join('')}</div></div>
      <div class="grade g2">
        <div class="cartao"><h2>Quando falar</h2>
          ${chk('retas', 'Só falar nas retas (espera a curva acabar)')}${chk('freada', 'Nunca falar durante uma freada')}${chk('prioridade', 'Volta inválida e combustível passam na frente')}
          <label class="fraco" style="display:block;margin-top:8px;font-size:13px">Intervalo mínimo entre avisos</label>
          <select class="campo-largo" data-mudar="sp-sel" data-campo="intervalo" style="margin-top:4px">${[2, 4, 8, 15].map((n) => `<option value="${n}" ${Number(c.intervalo) === n ? 'selected' : ''}>${n} segundos</option>`).join('')}</select>
        </div>
        <div class="cartao"><h2>Onde tocar</h2>
          <div class="grupo-op">${op('saida', 'pc', 'No PC', 'Alto-falante ou fone do PC', c.saida)}${op('saida', 'celular', 'No celular', 'Com a tela do Axtel aberta no celular', c.saida)}${op('saida', 'ambos', 'Nos dois', 'PC e celular juntos', c.saida)}</div>
          <h2 style="margin-top:16px">Atalhos durante a corrida</h2>
          <div class="linha" style="min-height:40px"><span style="flex:1">Repetir o último aviso</span><kbd>F9</kbd></div>
          <div class="linha" style="min-height:40px"><span style="flex:1">Silenciar por 1 volta</span><kbd>F10</kbd></div>
          <div class="linha" style="min-height:40px"><span style="flex:1">Ligar ou desligar o spotter</span><kbd>Ctrl + F10</kbd></div>
          <p class="fraco" style="font-size:12.5px;margin:6px 0 0">${(SP.cfgGeral || {}).atalhos ? 'Ligados: funcionam com o jogo na frente.' : 'Desligados.'} Ligue ou desligue em <a href="#/config">Configurações</a>: enquanto ligados, o jogo não recebe F9 e F10. Dá para ligar a um botão do volante pelo programa do volante.</p>
        </div>
      </div>
      <div class="cartao"><h2>O que ele falou</h2><div id="falados"></div></div>`;
  },
  depois() {
    desenharFalados();
    desenharAtalhoSpotter();
    if ('speechSynthesis' in window && !speechSynthesis.getVoices().length) speechSynthesis.onvoiceschanged = () => { if (lerRota().nome === 'spotter') render(true); speechSynthesis.onvoiceschanged = null; };
  },
};

const VIVO_POS = ['Dianteiro esq.', 'Dianteiro dir.', 'Traseiro esq.', 'Traseiro dir.'];
const CORES_BANDEIRA = { verde: 'ok', azul: '', amarela: 'amarela', branca: '', vermelha: 'ruim', preta: 'ruim', quadriculada: '', penalidade: 'ruim' };
function fmtTempoRestante(s) {
  if (s == null) return '—';
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`;
}
const num = (v, casas = 1) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }));
function corPneu(t) { return t == null ? 'var(--borda)' : t < 60 ? 'var(--azul)' : t <= 100 ? 'var(--verde)' : t <= 110 ? 'var(--amarelo)' : 'var(--vermelho)'; }
function htmlVolante() {
  return `<svg viewBox="-110 -110 220 220" width="130" height="130" aria-hidden="true">
    <path d="M0,-104 A104,104 0 0 1 0,104 A104,104 0 0 1 0,-104" fill="none" stroke="#252C36" stroke-width="3" stroke-dasharray="2 7"/>
    <path id="v-vol-arco" d="" fill="none" stroke="#FF6A2B" stroke-width="4" stroke-linecap="round"/>
    <g id="v-vol-g">
      <circle r="82" fill="none" stroke="#C9CED6" stroke-width="16"/>
      <path d="M-75,4 L-30,10 M75,4 L30,10" stroke="#5A6474" stroke-width="16" stroke-linecap="round"/>
      <path d="M0,34 L0,74" stroke="#5A6474" stroke-width="16" stroke-linecap="round"/>
      <circle r="34" fill="#1B212A" stroke="#5A6474" stroke-width="3"/>
      <text y="6" text-anchor="middle" font-size="15" font-weight="800" fill="#E7EAEE" font-family="Segoe UI,system-ui" letter-spacing="1">AX</text>
      <rect x="-6" y="-98" width="12" height="30" rx="3" fill="#FF6A2B"/>
    </g></svg>`;
}
function desenharVivo(d) {
  const el = $('#vivo');
  if (!el) return;
  if (!d || !d.jogo) {
    const s = E.status;
    if (el.dataset.modo !== 'vazio') {
      el.dataset.modo = 'vazio';
      el.innerHTML = `<div class="cartao vazio-grande"><h2 id="vv-tit"></h2><p class="fraco" id="vv-det"></p></div>`;
    }
    $('#vv-tit').textContent = s ? (s.nivel === 'verde' ? 'Lendo o jogo…' : s.titulo) : 'Axtel fechado';
    $('#vv-det').textContent = s ? (s.nivel === 'verde' ? '' : s.detalhe) : 'Abra o Axtel de novo pelo atalho.';
    return;
  }
  if (el.dataset.modo !== 'vivo') {
    el.dataset.modo = 'vivo';
    E.vivoMapa = null;
    const chip = (id, rot) => `<div class="av-chip"><small>${rot}</small><b id="${id}">—</b></div>`;
    const t = (id, rot, cls = '') => `<div><small>${rot}</small><b id="${id}" class="${cls}">—</b></div>`;
    el.innerHTML = `<div class="cartao"><div class="av-cab">
        <div style="flex:1 1 320px;min-width:0"><div class="av-carro" id="v-carro"></div><div class="fraco" id="v-sub"></div></div>
        <div class="av-chips">${chip('v-posicao', 'Posição')}${chip('v-voltas', 'Volta')}${chip('v-restante', 'Tempo restante')}${chip('v-frente', 'À frente')}${chip('v-tras', 'Atrás')}</div>
        <a class="btn so-painel" id="v-sessao">Abrir esta sessão</a></div></div>
      <div class="av-grade">
        <div class="cartao"><div class="av-rot">Volta atual · <span id="v-valida"></span></div>
          <div class="vivo-grande" id="v-atual"></div>
          <div class="vivo-delta" id="v-delta" style="margin-top:6px"></div><small class="fraco">em relação à melhor volta da sessão</small>
          <div class="av-tempos">${t('v-ultima', 'Última')}${t('v-melhor', 'Melhor', 'roxo')}${t('v-previsao', 'Previsão')}</div>
          <div class="av-tempos">${t('v-p1', 'Parcial 1')}${t('v-p2', 'Parcial 2')}${t('v-p3', 'Parcial 3')}</div></div>
        <div class="cartao"><div class="av-rot">Volante e pedais</div>
          <div class="av-volante"><div style="text-align:center;flex:1">${htmlVolante()}
            <div class="mono" style="font-size:18px;margin-top:2px" id="v-vol-txt">—</div></div>
            <div class="av-pedais">
              <div class="av-pv"><div class="av-barra"><i id="v-embr" style="background:var(--azul)"></i></div>Embr.</div>
              <div class="av-pv"><div class="av-barra"><i id="v-freio" style="background:var(--vermelho)"></i></div>Freio</div>
              <div class="av-pv"><div class="av-barra"><i id="v-acel" style="background:var(--verde)"></i></div>Acel.</div></div></div>
          <div class="linha" id="v-eletronica" style="margin-top:10px;font-size:12.5px"></div></div>
        <div class="cartao"><div class="av-rot">Motor</div>
          <div class="av-rpm" id="v-rpm">${'<i></i>'.repeat(12)}</div>
          <div class="linha" style="align-items:flex-end;gap:18px">
            <div><small class="fraco">Marcha</small><div class="av-marcha" id="v-marcha"></div></div>
            <div><small class="fraco">Velocidade</small><div class="mono" style="font-size:36px;font-weight:600"><span id="v-vel"></span><span class="fraco" style="font-size:15px"> km/h</span></div>
              <div class="mono fraco" id="v-rpm-txt"></div></div></div>
          <div class="av-lista" style="margin-top:14px"><span>Água</span><b id="v-agua">—</b><span>Óleo</span><b id="v-oleo">—</b><span>Velocidade máx. na volta</span><b id="v-velmax">—</b></div></div>
      </div>
      <div class="av-grade">
        <div class="cartao"><div class="av-rot">Pneus · temperatura e pressão</div>
          <div class="av-pneus">${VIVO_POS.map((n, k) => `<div class="av-pneu"><small>${n}</small><b id="v-pt${k}">—</b><small id="v-pp${k}">—</small><div class="av-faixa" id="v-pf${k}"></div></div>`).join('')}</div>
          <div class="fraco" style="font-size:12.5px;margin-top:8px" id="v-pneus-info"></div></div>
        <div class="cartao"><div class="av-rot">Combustível</div>
          <div class="linha" style="align-items:flex-end"><div class="mono" style="font-size:34px;font-weight:600"><span id="v-comb"></span> <span class="fraco" style="font-size:15px" id="v-comb-un">L</span></div>
            <span class="esp"></span><span class="selo" id="v-comb-selo" hidden></span></div>
          <div class="pedal" style="height:10px;margin:8px 0 12px"><i id="v-comb-barra" style="width:0;background:var(--amarelo)"></i></div>
          <div class="av-lista"><span>Consumo por volta</span><b id="v-cpv">—</b><span>Voltas com o tanque</span><b id="v-vcomb">—</b><span>Faltam na corrida</span><b id="v-faltam">—</b></div>
          <div class="av-rot" style="margin-top:16px">Condições</div>
          <div class="av-lista"><span>Pista</span><b id="v-tpista">—</b><span>Ar</span><b id="v-tar">—</b><span>Clima</span><b id="v-clima">—</b></div></div>
        <div class="cartao"><div class="av-rot">Posição na pista</div>
          <svg id="v-mapa" viewBox="0 0 300 170" class="av-mapa"></svg>
          <div class="linha fraco" style="font-size:12.5px"><span id="v-npos"></span><span class="esp"></span><span id="v-mapa-info"></span></div></div>
      </div>`;
  }
  const i = d.info || {};
  const set = (id, v) => { const x = $('#' + id); if (x) x.textContent = v; };
  const html = (id, v) => { const x = $('#' + id); if (x) x.innerHTML = v; };
  set('v-carro', d.carro);
  const selos = [`<span class="selo ok">${esc(d.tipo)}</span>`];
  if (i.bandeira) selos.push(`<span class="selo ${CORES_BANDEIRA[i.bandeira] || ''}">bandeira ${esc(i.bandeira)}</span>`);
  if (i.limitador) selos.push('<span class="selo">limitador ligado</span>');
  html('v-sub', `${i.classe ? esc(i.classe) + ' · ' : ''}${esc(d.pista)} · ${esc(d.jogo)} ${selos.join(' ')}`);
  $('#v-sessao').href = '#/sessao/' + d.sessao_id;
  html('v-posicao', i.posicao ? `P${i.posicao}${i.carros ? `<span class="fraco" style="font-size:13px">/${i.carros}</span>` : ''}` : '—');
  html('v-voltas', `${d.volta}${i.voltas_total ? `<span class="fraco" style="font-size:13px">/${i.voltas_total}</span>` : ''}`);
  set('v-restante', fmtTempoRestante(i.tempo_restante_s));
  const gap = (id, ms, sinal) => { const x = $('#' + id); if (!x) return; x.textContent = ms == null ? '—' : sinal + (ms / 1000).toFixed(3).replace('.', ','); x.className = ms == null ? '' : sinal === '+' ? 'vermelho' : 'verde'; };
  gap('v-frente', i.gap_frente_ms, '+'); gap('v-tras', i.gap_tras_ms, '−');
  const vv = $('#v-valida');
  vv.textContent = d.volta_valida ? 'válida' : (d.motivo || 'inválida');
  vv.className = d.volta_valida ? 'verde' : 'vermelho';
  set('v-atual', fmtVolta(d.atual_ms));
  const dl = $('#v-delta');
  dl.textContent = d.delta_ms == null ? '—' : fmtDelta(d.delta_ms);
  dl.className = 'vivo-delta ' + (d.delta_ms == null ? 'fraco' : d.delta_ms > 0 ? 'vermelho' : 'verde');
  set('v-ultima', d.ultima_ms ? fmtVolta(d.ultima_ms) : '—');
  set('v-melhor', d.melhor_ms ? fmtVolta(d.melhor_ms) : '—');
  set('v-previsao', i.previsao_ms ? fmtVolta(i.previsao_ms) : '—');
  set('v-p1', d.p1 != null ? fmtParcial(d.p1) : '—');
  set('v-p2', d.p2 != null ? fmtParcial(d.p2) : '—');
  set('v-p3', '—');
  // volante: positivo = direita
  const graus = i.volante_graus != null ? i.volante_graus : (i.volante != null ? i.volante * 450 : null);
  const g = $('#v-vol-g');
  if (g) g.setAttribute('transform', `rotate(${graus == null ? 0 : Math.max(-540, Math.min(540, graus))})`);
  const arco = $('#v-vol-arco');
  if (arco) {
    const a = graus == null ? 0 : Math.max(-179, Math.min(179, graus)) * Math.PI / 180;
    const x = (104 * Math.sin(a)).toFixed(1), y = (-104 * Math.cos(a)).toFixed(1);
    arco.setAttribute('d', Math.abs(a) < 0.01 ? '' : `M0,-104 A104,104 0 0 ${a > 0 ? 1 : 0} ${x},${y}`);
  }
  const lado = (v) => (Math.abs(v) < 0.5 ? 'centro' : v < 0 ? 'esquerda' : 'direita');
  set('v-vol-txt', i.volante_graus != null ? `${Math.abs(i.volante_graus)}° ${lado(i.volante_graus)}` : i.volante != null ? `${Math.round(Math.abs(i.volante) * 100)}% ${lado(i.volante * 100)}` : 'sem dado do jogo');
  $('#v-acel').style.height = d.acel * 100 + '%';
  $('#v-freio').style.height = d.freio * 100 + '%';
  $('#v-embr').style.height = (i.embreagem || 0) * 100 + '%';
  const ele = [];
  if (i.tc != null) ele.push(`<span class="selo">TC ${esc(i.tc)}</span>`);
  if (i.abs != null) ele.push(`<span class="selo">ABS ${esc(i.abs)}</span>`);
  if (i.bias_freio != null) ele.push(`<span class="selo">Freio ${Math.round(i.bias_freio * 100)}% dianteiro</span>`);
  html('v-eletronica', ele.join(''));
  // motor
  E.rpmMaxVisto = Math.max(E.rpmMaxVisto || 0, d.rpm || 0);
  const rmax = i.rpm_max || E.rpmMaxVisto || 1;
  const f = Math.max(0, Math.min(1, (d.rpm || 0) / rmax));
  $$('#v-rpm i').forEach((x, k) => {
    const lim = (k + 1) / 12;
    const acesa = f >= lim - 1 / 24;
    x.style.background = !acesa ? '' : f > 0.97 ? 'var(--vermelho)' : lim <= 0.6 ? 'var(--verde)' : lim <= 0.85 ? 'var(--amarelo)' : 'var(--vermelho)';
  });
  set('v-marcha', d.marcha < 0 ? 'R' : d.marcha === 0 ? 'N' : d.marcha);
  set('v-vel', d.vel);
  set('v-rpm-txt', `${(d.rpm || 0).toLocaleString('pt-BR')}${i.rpm_max ? ' / ' + i.rpm_max.toLocaleString('pt-BR') : ''} rpm`);
  set('v-agua', i.agua != null ? num(i.agua, 0) + ' °C' : '—');
  set('v-oleo', i.oleo != null ? num(i.oleo, 0) + ' °C' : '—');
  set('v-velmax', i.vel_max ? i.vel_max + ' km/h' : '—');
  // pneus
  for (let k = 0; k < 4; k++) {
    const tt = i.pneus_temp ? i.pneus_temp[k] : null, pp = i.pneus_psi ? i.pneus_psi[k] : null;
    const b = $('#v-pt' + k);
    if (!b) continue;
    b.textContent = tt != null ? Math.round(tt) + '°' : '—';
    b.style.color = tt != null && tt > 100 ? corPneu(tt) : '';
    set('v-pp' + k, pp != null ? num(pp, 1) + ' psi' : (tt != null ? 'pressão: —' : 'sem dado do jogo'));
    $('#v-pf' + k).style.background = corPneu(tt);
  }
  const pinfo = [];
  if (i.composto) pinfo.push('Composto: ' + esc(i.composto));
  if (i.freios_temp) pinfo.push('freios ' + i.freios_temp.map((x) => Math.round(x)).join(' / ') + ' °C');
  html('v-pneus-info', pinfo.join(' · '));
  // combustível
  const forza = d.jogo === 'Forza';
  set('v-comb', num(d.combustivel, 1));
  set('v-comb-un', forza ? '%' : 'L');
  const cap = forza ? 100 : i.comb_capacidade;
  $('#v-comb-barra').style.width = cap ? Math.min(100, (d.combustivel / cap) * 100) + '%' : '0';
  set('v-cpv', i.comb_por_volta != null ? num(i.comb_por_volta, 1) + (forza ? ' %' : ' L') : '—');
  set('v-vcomb', i.voltas_comb != null ? num(i.voltas_comb, 1) : '—');
  set('v-faltam', i.voltas_restantes != null ? plural(i.voltas_restantes, 'volta', 'voltas') : '—');
  const cs = $('#v-comb-selo');
  if (i.voltas_comb != null && i.voltas_restantes != null) {
    const sobra = i.voltas_comb - i.voltas_restantes;
    cs.hidden = false;
    cs.className = 'selo ' + (sobra >= 0 ? 'ok' : 'ruim');
    cs.textContent = sobra >= 0 ? `dá até o fim + ${num(sobra, 1)} voltas` : `faltam ${num(-sobra, 1)} voltas de combustível`;
  } else cs.hidden = true;
  set('v-tpista', i.pista_temp != null ? num(i.pista_temp, 0) + ' °C' : '—');
  set('v-tar', i.ar_temp != null ? num(i.ar_temp, 0) + ' °C' : '—');
  set('v-clima', i.clima || '—');
  // mapa
  set('v-npos', Math.round(d.npos * 100) + '% da volta');
  desenharMapaVivo(i.mapa, d.jogo);
}
function desenharMapaVivo(m, jogo) {
  const svg = $('#v-mapa');
  if (!svg) return;
  if (!m || !m.contorno || m.contorno.length < 5) {
    if (E.vivoMapa !== 'vazio') {
      E.vivoMapa = 'vazio';
      svg.innerHTML = `<text x="150" y="88" text-anchor="middle" fill="#8C95A2" font-size="12">${jogo === 'iRacing' ? 'O iRacing não manda a posição do carro' : 'O mapa aparece depois da primeira volta'}</text>`;
    }
    set_('v-mapa-info', '');
    return;
  }
  const c = m.contorno;
  const chave = c.length + ':' + c[0].join(',') + (m.completo ? 'c' : '');
  if (E.vivoMapa !== chave) {
    E.vivoMapa = chave;
    const xs = c.map((p) => p[0]), zs = c.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
    const esc_ = Math.min(280 / ((x1 - x0) || 1), 150 / ((z1 - z0) || 1));
    const ox = (300 - (x1 - x0) * esc_) / 2, oz = (170 - (z1 - z0) * esc_) / 2;
    E.vivoProj = (p) => [(ox + (p[0] - x0) * esc_).toFixed(1), (oz + (z1 - p[1]) * esc_).toFixed(1)];
    const d = c.map((p, k) => (k ? 'L' : 'M') + E.vivoProj(p).join(',')).join('') + (m.completo ? 'Z' : '');
    svg.innerHTML = `<path d="${d}" fill="none" stroke="#3a4250" stroke-width="9" stroke-linejoin="round"/><g id="v-mapa-outros"></g>
      <circle id="v-mapa-eu" r="7" fill="#FF6A2B" stroke="#0D1015" stroke-width="3"/>`;
  }
  const eu = E.vivoProj(m.eu);
  const ce = $('#v-mapa-eu');
  if (ce) { ce.setAttribute('cx', eu[0]); ce.setAttribute('cy', eu[1]); }
  const og = $('#v-mapa-outros');
  if (og) og.innerHTML = (m.outros || []).map((p) => { const q = E.vivoProj(p); return `<circle cx="${q[0]}" cy="${q[1]}" r="4.5" fill="#8C95A2"/>`; }).join('');
  set_('v-mapa-info', m.outros && m.outros.length ? plural(m.outros.length, 'outro carro', 'outros carros') : '');
}
function set_(id, v) { const x = $('#' + id); if (x) x.textContent = v; }

// ------------------------------------------------------------------ CALENDÁRIO
const COR_JOGO = { 'AC EVO': 'var(--destaque)', 'Assetto Corsa': 'var(--azul)', ACC: 'var(--verde)', iRacing: '#C084FC', 'Automobilista 2': '#F472B6', 'F1 25': '#F87171', Forza: '#FACC15' };
const corJogo = (j) => COR_JOGO[j] || 'var(--amarelo)';
const COR_MELHORA = { tempo: '#4ADE80', marco: '#F2A93B', consistencia: '#5AA9F2', limpas: '#C4CAD3' };
function hojeISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function fmtDia(iso) { const [, m, d] = iso.split('-'); return `${d}/${m}`; }
function somaMes(mes, n) {
  let [a, m] = mes.split('-').map(Number);
  m += n;
  while (m < 1) { m += 12; a -= 1; }
  while (m > 12) { m -= 12; a += 1; }
  return `${a}-${String(m).padStart(2, '0')}`;
}
function urlCalendario(mes, jogo, dia) {
  const p = new URLSearchParams();
  if (dia) p.set('dia', dia);
  if (jogo) p.set('jogo', jogo);
  return `#/calendario/${mes}` + (p.toString() ? '?' + p : '');
}

PAGINAS.calendario = {
  async html(r) {
    const hoje = hojeISO();
    const mes = /^\d{4}-\d{2}$/.test(r.arg[0] || '') ? r.arg[0] : hoje.slice(0, 7);
    const jogo = r.q.jogo || '';
    const [j, d] = await Promise.all([api('/api/jogos'), api(`/api/calendario?mes=${mes}&jogo=${enc(jogo)}`)]);
    let dia = r.q.dia && r.q.dia.startsWith(mes) ? r.q.dia : null;
    if (!dia) {
      const comDados = Object.keys(d.dias).sort();
      if (hoje.startsWith(mes) && d.dias[hoje]) dia = hoje;
      else if (comDados.length) dia = comDados[comDados.length - 1];
      else if (hoje.startsWith(mes)) dia = hoje;
    }
    E.cal = { mes, jogo, dia, dias: d.dias, tok: 0 };
    const [ano, m] = mes.split('-').map(Number);
    const primeiro = new Date(ano, m - 1, 1);
    const vazios = (primeiro.getDay() + 6) % 7; // semana começa na segunda
    const nDias = new Date(ano, m, 0).getDate();
    const titulo = primeiro.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    const celulas = [];
    for (let i = 0; i < vazios; i++) celulas.push('<div class="dia vazio" aria-hidden="true"></div>');
    for (let n = 1; n <= nDias; n++) {
      const iso = `${mes}-${String(n).padStart(2, '0')}`;
      const x = d.dias[iso];
      const ml = x && x.melhoras && E.calDestacar !== false ? x.melhoras : null;
      celulas.push(`<button class="dia ${iso === dia ? 'on' : ''} ${iso === hoje ? 'hoje' : ''} ${ml ? 'melhora' : ''}" data-acao="dia" data-d="${iso}"
        aria-label="${n} de ${titulo}${x ? ': ' + plural(x.sessoes, 'sessão', 'sessões') : ''}${ml ? ', dia de melhora' : ''}">
        <span class="n"><b>${n}</b>${x && x.recordes ? '<span class="estrela" title="recorde pessoal">★</span>' : ''}</span>
        ${x ? `<span class="info">${plural(x.sessoes, 'sessão', 'sessões')}</span><span class="info">${fmtDur(x.tempo_s)} · ${x.voltas} voltas</span>
        ${ml ? `<span class="info" style="color:${COR_MELHORA[ml[0].tipo]};font-weight:700">${esc(ml[0].curto)}${ml.length > 1 ? ' +' + (ml.length - 1) : ''}</span>` : ''}
        <span class="bolas">${x.jogos.map((g) => `<i class="bola" style="background:${corJogo(g)}" title="${esc(g)}"></i>`).join('')}</span>` : ''}
      </button>`);
    }
    const t = d.totais;
    const anterior = somaMes(mes, -1), proximo = somaMes(mes, 1);
    return `<h1>Calendário</h1><p class="sub">Seu histórico de corridas por data. Clique num dia para ver o resumo logo abaixo.</p>
      <div class="cartao">
        <div class="cal-topo">
          <a class="btn" href="${urlCalendario(anterior, jogo)}" aria-label="Mês anterior">‹</a>
          <span class="cal-mes">${esc(titulo)}</span>
          <a class="btn" href="${urlCalendario(proximo, jogo)}" aria-label="Próximo mês">›</a>
          ${mes !== hoje.slice(0, 7) ? `<a class="btn" href="${urlCalendario(hoje.slice(0, 7), jogo)}">Hoje</a>` : ''}
          <button class="btn" data-acao="cal-destacar" aria-pressed="${E.calDestacar !== false}" style="border-color:#2F6B45;color:#6EE7A0">▲ ${E.calDestacar !== false ? 'Destacando dias de melhora' : 'Destacar dias de melhora'}</button>
          <span class="esp"></span>
          <span class="fraco" style="font-size:12.5px">${t.sessoes ? `${plural(t.sessoes, 'sessão', 'sessões')} · ${t.voltas} voltas · ${fmtDur(t.tempo_s)} no mês` : 'Nenhuma corrida neste mês'}</span>
        </div>
        <div class="chips" style="margin-top:12px">
          <a class="chip ${!jogo ? 'on' : ''}" href="${urlCalendario(mes, '')}" style="padding:7px 14px;min-width:0"><b style="font-size:13px">Todos os jogos</b></a>
          ${j.com_dados.map((g) => `<a class="chip ${g === jogo ? 'on' : ''}" href="${urlCalendario(mes, g)}" style="padding:7px 14px;min-width:0"><b style="font-size:13px"><i class="bola" style="background:${corJogo(g)};margin-right:6px"></i>${esc(g)}</b></a>`).join('')}
        </div>
        <div class="legenda" style="margin-top:10px"><b class="verde">Dias de melhora no mês: ${Object.values(d.dias).filter((x) => x.melhoras).length}</b>
          <span><b style="color:${COR_MELHORA.tempo}">▲</b> ganho de 0,3 s ou mais</span><span><b style="color:${COR_MELHORA.marco}">◎</b> marco (abaixo de um segundo cheio)</span>
          <span><b style="color:${COR_MELHORA.consistencia}">◆</b> consistência recorde</span><span><b style="color:${COR_MELHORA.limpas}">✓</b> 95% das voltas válidas</span><span><b class="roxo">★</b> recorde pessoal</span></div>
        <div class="cal">${['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'].map((x) => `<div class="sem">${x}</div>`).join('')}${celulas.join('')}</div>
        ${d.meses_com_dados.length && !t.sessoes ? `<p class="fraco" style="margin:12px 0 0;font-size:12.5px">Meses com corridas: ${d.meses_com_dados.map((x) => `<a href="${urlCalendario(x, jogo)}">${new Date(x + '-15T12:00').toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}</a>`).join(' · ')}</p>` : ''}
      </div>
      <div id="resumo-dia"></div>`;
  },
  depois() { desenharResumoDia(false); },
};

async function desenharResumoDia(rolar) {
  const C = E.cal;
  const box = $('#resumo-dia');
  if (!C || !box) return;
  $$('.cal .dia[data-d]').forEach((b) => b.classList.toggle('on', b.dataset.d === C.dia));
  history.replaceState(null, '', urlCalendario(C.mes, C.jogo, C.dia));
  if (!C.dia) { box.innerHTML = ''; return; }
  const tok = ++C.tok;
  const d = await api(`/api/dia?data=${C.dia}&jogo=${enc(C.jogo)}`);
  if (tok !== C.tok || E.cal !== C) return;
  const t = d.totais;
  const titulo = new Date(C.dia + 'T12:00').toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const filtro = C.jogo ? ` no ${esc(C.jogo)}` : '';
  const listaDia = '#/sessoes?' + new URLSearchParams({ data: C.dia, ...(C.jogo ? { jogo: C.jogo } : {}) });
  box.innerHTML = !t.sessoes ? `<div class="cartao resumo-dia"><h2 style="text-transform:capitalize">${esc(titulo)}</h2>
      <p class="fraco" style="margin:0">Nenhuma corrida neste dia${filtro}.</p></div>`
    : `<div class="cartao resumo-dia">
      <div class="linha"><h2 style="margin:0;text-transform:capitalize">${esc(titulo)}</h2><span class="esp"></span>
        <a class="btn" href="${listaDia}">Ver o dia na lista de Sessões</a></div>
      <div class="kpis" style="margin:14px 0 6px">
        <div class="kpi"><small>Sessões</small><b>${t.sessoes}</b></div>
        <div class="kpi"><small>Voltas</small><b>${t.voltas}</b><span>${t.validas} válidas</span></div>
        <div class="kpi"><small>Tempo na pista</small><b>${fmtDur(t.tempo_s)}</b></div>
        <div class="kpi"><small>Distância</small><b>${km(t.distancia_km)}</b></div>
        <div class="kpi"><small>Recordes</small><b class="roxo">${t.recordes}</b></div>
      </div>
      ${d.melhoras && d.melhoras.length ? `<div style="background:#12201A;border:1px solid #2F6B45;border-radius:12px;padding:12px 14px;margin-bottom:10px">
        <b class="verde" style="font-size:12.5px;letter-spacing:.05em;text-transform:uppercase">Melhoras deste dia</b>
        ${d.melhoras.map((m) => `<div class="linha" style="align-items:baseline;margin-top:8px"><i class="bola" style="background:${COR_MELHORA[m.tipo]}"></i><div><b>${esc(m.titulo)}</b><div class="fraco" style="font-size:13px">${esc(m.texto)}</div></div></div>`).join('')}</div>` : ''}
      <div>${d.sessoes.slice().reverse().map((s) => `<div class="sessao-dia">
        <span class="mono fraco">${new Date(s.inicio).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
        <i class="bola" style="background:${corJogo(s.jogo)}"></i>
        <div style="flex:1;min-width:180px"><b>${esc(s.carro)} · ${esc(s.pista)}</b>
          <div class="fraco" style="font-size:12.5px">${esc(s.jogo)} · ${esc(s.tipo)} · ${s.voltas} voltas (${s.validas} válidas) · ${fmtDur(s.tempo_s)}</div></div>
        <div><small class="fraco">melhor</small> <span class="mono ${s.recorde ? 'roxo' : ''}">${fmtVolta(s.melhor_ms)}</span> ${s.recorde ? '<span class="selo pb">recorde</span>' : ''}</div>
        <a class="btn pri" href="#/sessao/${s.id}">Abrir sessão →</a>
      </div>`).join('')}</div>
      <div class="linha" style="margin-top:12px">${d.jogos.map((g) => `<a class="btn" href="#/jogo/${enc(g)}">Estatísticas do ${esc(g)}</a>`).join('')}</div>
    </div>`;
  if (rolar) box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ------------------------------------------------------------------ ANOTAÇÕES
function atualizarNavPend(lista) {
  const n = lista.filter((p) => !p.feita).length;
  const el = $('#nav-pend');
  if (el) { el.hidden = !n; el.textContent = n; }
}
async function recarregarPendencias() {
  const d = await api('/api/pendencias');
  E.pend = d.pendencias;
  atualizarNavPend(E.pend);
  desenharPendencias();
}

PAGINAS.anotacoes = PAGINAS.pendencias = {
  async html() {
    const d = await api('/api/pendencias');
    E.pend = d.pendencias;
    E.pendEdit = null;
    E.pendApagar = null;
    atualizarNavPend(E.pend);
    return `<h1>Anotações</h1><p class="sub">Suas anotações sobre o Axtel e os treinos: ideias, coisas para lembrar e o que falta fazer. Ficam salvas no seu PC.</p>
      <div class="cartao"><h2>Nova anotação</h2>
        <input class="campo-largo" id="pend-texto" maxlength="300" placeholder="Anotação (Enter adiciona)">
        <textarea class="campo-largo" id="pend-nota" maxlength="2000" placeholder="Detalhes (opcional)" style="margin-top:8px"></textarea>
        <div class="linha" style="margin-top:8px"><button class="btn pri" data-acao="pend-add">Adicionar</button><span id="pend-msg" class="fraco" style="font-size:12.5px"></span></div>
      </div>
      <div class="cartao" id="pend-lista"></div>`;
  },
  depois() { desenharPendencias(); },
};

function itemPendencia(p) {
  const editando = E.pendEdit === p.id;
  const apagando = E.pendApagar === p.id;
  const corpo = editando
    ? `<input class="campo-largo" id="pend-e-texto" maxlength="300" value="${esc(p.texto)}">
       <textarea class="campo-largo" id="pend-e-nota" maxlength="2000" style="margin-top:6px" placeholder="Detalhes (opcional)">${esc(p.nota || '')}</textarea>`
    : `<b>${esc(p.texto)}</b>${p.nota ? `<div class="fraco" style="white-space:pre-wrap">${esc(p.nota)}</div>` : ''}
       <small class="fraco">anotada em ${fmtData(p.criada)}${p.feita && p.concluida ? ' · concluída em ' + fmtData(p.concluida) : ''}</small>`;
  const acoes = editando
    ? `<button class="btn pri" data-acao="pend-salvar" data-id="${p.id}">Salvar</button><button class="btn" data-acao="pend-cancelar">Cancelar</button>`
    : apagando
      ? `<span class="fraco" style="font-size:12.5px;align-self:center">Apagar?</span><button class="btn perigo" data-acao="pend-apagar-sim" data-id="${p.id}">Sim, apagar</button><button class="btn" data-acao="pend-cancelar">Não</button>`
      : `${p.feita ? '' : `<button class="btn" data-acao="pend-editar" data-id="${p.id}">Editar</button>`}<button class="btn perigo" data-acao="pend-apagar" data-id="${p.id}">Apagar</button>`;
  return `<div class="pend ${p.feita ? 'feita' : ''}">
    <input type="checkbox" class="marca" style="margin-top:2px" data-mudar="pend-feita" data-id="${p.id}" ${p.feita ? 'checked' : ''} aria-label="Marcar como concluída: ${esc(p.texto)}">
    <div class="corpo">${corpo}</div><div class="acoes">${acoes}</div></div>`;
}

function desenharPendencias() {
  const box = $('#pend-lista');
  if (!box) return;
  const abertas = E.pend.filter((p) => !p.feita), feitas = E.pend.filter((p) => p.feita);
  box.innerHTML = `<h2>Anotações abertas (${abertas.length})</h2>
    ${abertas.length ? abertas.map(itemPendencia).join('') : '<div class="fraco">Nenhuma anotação aberta.</div>'}
    ${feitas.length ? `<hr><button class="btn" data-acao="pend-ver-feitas">${E.verFeitas ? 'Esconder' : 'Mostrar'} concluídas (${feitas.length})</button>
      ${E.verFeitas ? `<div style="margin-top:8px">${feitas.map(itemPendencia).join('')}</div>` : ''}` : ''}`;
  if (E.pendEdit) { const i = $('#pend-e-texto'); if (i) i.focus(); }
}

async function adicionarPendencia() {
  const texto = $('#pend-texto').value.trim();
  const msg = $('#pend-msg');
  if (!texto) { msg.textContent = 'Escreva a anotação primeiro.'; $('#pend-texto').focus(); return; }
  const r = await post('/api/pendencias/nova', { texto, nota: $('#pend-nota').value });
  if (!r.ok) { msg.textContent = r.erro || 'Não consegui salvar.'; return; }
  $('#pend-texto').value = '';
  $('#pend-nota').value = '';
  msg.textContent = 'Anotado.';
  await recarregarPendencias();
}

// ------------------------------------------------------------------ escolha de carro + pista (Setups, Desafios)
function chaveCombo(c) { return [c.jogo, c.carro, c.pista].join('|'); }
function seletorCombo(combos, atual, acao) {
  if (!combos.length) return '';
  return `<select class="campo-largo" data-mudar="${acao}" aria-label="Carro e pista">${combos.map((c) => `<option value="${esc(chaveCombo(c))}" ${chaveCombo(c) === atual ? 'selected' : ''}>${esc(c.carro)} · ${esc(c.pista)} · ${esc(c.jogo)}</option>`).join('')}</select>`;
}
function lerCombo(r, combos) {
  const k = r.q.combo || recuperar('axtel.combo', '');
  const c = combos.find((x) => chaveCombo(x) === k) || combos[0];
  return c || null;
}

// ------------------------------------------------------------------ SETUPS
PAGINAS.setups = {
  async html(r) {
    const base = await api('/api/setups');
    const c = lerCombo(r, base.combos);
    if (!c) return `<h1>Setups</h1><div class="cartao vazio-grande"><h2>Nenhuma sessão ainda</h2><p class="fraco">Os setups ficam ligados a um carro e uma pista. Corra uma sessão primeiro.</p></div>`;
    E.combo_setup = c;
    const d = await api(`/api/setups?jogo=${enc(c.jogo)}&carro=${enc(c.carro)}&pista=${enc(c.pista)}`);
    E.setups = d.setups;
    const comp = (E.setupComparar || []).filter((id) => d.setups.some((s) => s.id === id));
    const edit = E.setupEditar;
    const formulario = (s) => `<div class="cartao" id="form-setup"><h2>${s ? 'Editar setup' : 'Registrar um setup'}</h2>
        <label class="fraco" style="font-size:13px">Nome</label>
        <input class="campo-largo" id="st-nome" maxlength="80" placeholder="Ex.: Interlagos seco v3" value="${esc(s ? s.nome : '')}">
        <label class="fraco" style="font-size:13px;display:block;margin-top:10px">Ajustes (um por linha, no formato nome = valor)</label>
        <textarea class="campo-largo" id="st-params" rows="7" placeholder="Asa traseira = 6&#10;Balanço de freio = 55,5%&#10;TC = 2&#10;Pressão dianteira = 26,0 psi">${esc(s ? s.parametros.map((p) => p[0] + (p[1] ? ' = ' + p[1] : '')).join('\n') : '')}</textarea>
        <label class="fraco" style="font-size:13px;display:block;margin-top:10px">Notas</label>
        <textarea class="campo-largo" id="st-notas" rows="2" placeholder="Como o carro ficou, condições da pista…">${esc(s ? s.notas : '')}</textarea>
        <div class="linha" style="margin-top:10px"><button class="btn pri" data-acao="st-salvar" data-id="${s ? s.id : ''}">Salvar setup</button>${s ? '<button class="btn" data-acao="st-cancelar">Cancelar</button>' : ''}<span id="st-msg" class="fraco"></span></div>
        <p class="fraco" style="font-size:12.5px;margin:8px 0 0">Depois, no detalhe de cada sessão, escolha qual setup foi usado. Os resultados aparecem aqui.</p></div>`;
    let tabelaComp = '';
    if (comp.length === 2) {
      const [a, b] = comp.map((id) => d.setups.find((s) => s.id === id));
      const nomes = [...new Set([...a.parametros, ...b.parametros].map((p) => p[0]))];
      const val = (s, n) => (s.parametros.find((p) => p[0] === n) || [, '—'])[1] || '—';
      tabelaComp = `<div class="cartao"><div class="linha"><h2 style="margin:0">${esc(a.nome)} × ${esc(b.nome)}</h2><span class="esp"></span><button class="btn" data-acao="st-comp-limpar">Fechar comparação</button></div>
        <div class="kpis" style="margin-top:12px">
          <div class="kpi"><small>Melhor volta</small><b>${fmtVolta(a.melhor_ms)}</b><span>${esc(a.nome)}</span></div>
          <div class="kpi"><small>Melhor volta</small><b>${fmtVolta(b.melhor_ms)}</b><span>${esc(b.nome)}</span></div>
          <div class="kpi"><small>Diferença das médias</small><b class="${a.media_melhores_ms && b.media_melhores_ms && b.media_melhores_ms > a.media_melhores_ms ? 'vermelho' : 'verde'}">${a.media_melhores_ms && b.media_melhores_ms ? fmtDelta(b.media_melhores_ms - a.media_melhores_ms) : '—'}</b><span>média das melhores de cada sessão</span></div></div>
        <div class="rolar"><table><thead><tr><th>Ajuste</th><th>${esc(a.nome)}</th><th>${esc(b.nome)}</th><th></th></tr></thead><tbody>
        ${nomes.map((n) => { const x = val(a, n), y = val(b, n); return `<tr><td>${esc(n)}</td><td class="mono">${esc(x)}</td><td class="mono">${esc(y)}</td><td>${x !== y ? '<span class="selo pb">mudou</span>' : ''}</td></tr>`; }).join('')}
        </tbody></table></div></div>`;
    }
    return `<h1>Setups</h1><p class="sub">Qual acerto do carro deu o melhor resultado em cada pista.</p>
      <div class="cartao escolha"><h2>Carro e pista</h2>${seletorCombo(base.combos, chaveCombo(c), 'st-combo')}</div>
      ${tabelaComp}
      ${d.setups.length ? `<div class="cartao"><div class="linha"><h2 style="margin:0">Setups de ${esc(c.carro)} em ${esc(c.pista)}</h2><span class="esp"></span><span class="fraco" style="font-size:12.5px">Marque dois para comparar</span></div>
        <div class="rolar" style="margin-top:8px"><table><thead><tr><th>Comparar</th><th>Setup</th><th>Sessões</th><th>Voltas</th><th>Melhor</th><th>Média das melhores</th><th>Última vez</th><th></th></tr></thead><tbody>
        ${d.setups.map((s) => `<tr class="${comp.includes(s.id) ? 'sel' : ''}"><td><input type="checkbox" class="marca" data-mudar="st-comp" data-id="${s.id}" ${comp.includes(s.id) ? 'checked' : ''} aria-label="Comparar ${esc(s.nome)}"></td>
          <td><b>${esc(s.nome)}</b>${s.notas ? `<br><span class="fraco" style="font-size:12.5px;white-space:normal">${esc(s.notas)}</span>` : ''}</td><td>${s.sessoes}</td><td>${s.voltas}</td>
          <td class="mono">${fmtVolta(s.melhor_ms)}</td><td class="mono">${fmtVolta(s.media_melhores_ms)}</td><td class="fraco">${s.ultima ? fmtData(s.ultima) : 'ainda não usado'}</td>
          <td><button class="btn" data-acao="st-editar" data-id="${s.id}">Editar</button> <button class="btn perigo" data-acao="st-apagar" data-id="${s.id}">Apagar</button></td></tr>`).join('')}
        </tbody></table></div></div>` : ''}
      ${formulario(edit ? d.setups.find((s) => s.id === edit) : null)}`;
  },
};

// ------------------------------------------------------------------ DESAFIOS E PLANO
PAGINAS.desafios = {
  async html(r) {
    const d = await api('/api/desafios');
    const c = lerCombo(r, d.combos);
    let plano = null;
    if (c) plano = await api(`/api/plano?jogo=${enc(c.jogo)}&carro=${enc(c.carro)}&pista=${enc(c.pista)}`);
    E.desafiosCombo = c;
    const abertos = d.desafios.filter((x) => !x.concluido), feitos = d.desafios.filter((x) => x.concluido);
    const cartaoDesafio = (x) => `<div class="aviso-item desafio ${x.concluido ? 'feito' : ''}">
        <div class="linha"><b style="flex:1">${esc(x.titulo)}</b>${x.concluido ? `<span class="selo ok">concluído em ${fmtData(x.concluido)}</span>` : ''}</div>
        <span class="fraco" style="font-size:12.5px">${esc(x.carro)} · ${esc(x.pista)} · ${esc(x.jogo)}</span>
        <div class="barra-prog"><i style="width:${x.pct}%"></i></div>
        <div class="linha"><span class="fraco" style="font-size:12.5px;flex:1">${esc(x.progresso_texto)}</span><button class="btn perigo" style="padding:3px 10px" data-acao="ds-apagar" data-id="${x.id}">Apagar</button></div></div>`;
    const tipoOpts = Object.entries(d.tipos).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
    return `<h1>Desafios e plano</h1><p class="sub">Metas que o Axtel acompanha sozinho com as suas voltas, e um plano de treino de 30 minutos.</p>
      ${!d.combos.length ? '<div class="cartao vazio-grande"><h2>Nenhuma sessão ainda</h2><p class="fraco">Corra uma sessão para o Axtel sugerir desafios e montar o plano.</p></div>' : `
      <div class="cartao escolha"><h2>Carro e pista do plano</h2>${seletorCombo(d.combos, chaveCombo(c), 'ds-combo')}</div>
      <div class="cartao"><h2>Plano de treino · ${plano && plano.ok ? plano.total_min + ' minutos' : ''}</h2>
        ${plano && plano.ok ? `<p class="fraco" style="margin:-4px 0 10px">Baseado na sessão de ${fmtData(plano.base.inicio)}: melhor ${fmtVolta(plano.base.melhor_ms)}, recorde ${fmtVolta(plano.base.pb_ms)}${plano.base.desvio_ms ? `, variação ±${(plano.base.desvio_ms / 1000).toFixed(3)} s` : ''}. <a href="#/sessao/${plano.base.id}">Abrir a sessão</a></p>
          ${plano.blocos.map((b) => `<div class="bloco-plano"><div><b class="mono" style="font-size:22px">${b.min}</b><br><span class="fraco" style="font-size:12px">minutos</span></div>
            <div><b>${esc(b.titulo)}</b><div class="amarelo" style="font-size:13px;margin:2px 0">Meta: ${esc(b.meta)}</div><div class="fraco" style="font-size:13.5px">${esc(b.texto)}</div></div></div>`).join('')}`
          : `<p class="fraco">${esc((plano && plano.erro) || '')}</p>`}
      </div>`}
      <div class="cartao"><h2>Desafios em andamento (${abertos.length})</h2>
        ${abertos.length ? `<div class="grade-avisos">${abertos.map(cartaoDesafio).join('')}</div>` : '<p class="fraco" style="margin:0">Nenhum desafio aberto. Escolha uma sugestão abaixo ou crie o seu.</p>'}
        ${feitos.length ? `<hr><button class="btn" data-acao="ds-ver-feitos">${E.verDesafiosFeitos ? 'Esconder' : 'Mostrar'} concluídos (${feitos.length})</button>${E.verDesafiosFeitos ? `<div class="grade-avisos" style="margin-top:10px">${feitos.map(cartaoDesafio).join('')}</div>` : ''}` : ''}
      </div>
      ${d.sugestoes.length ? `<div class="cartao"><h2>Sugestões do Axtel</h2><div class="grade-avisos">${d.sugestoes.map((s, i) => `<div class="aviso-item">
        <b>${esc(s.titulo)}</b><span class="fraco" style="font-size:12.5px">${esc(s.carro)} · ${esc(s.pista)} · ${esc(s.jogo)}</span>
        <div><button class="btn pri" data-acao="ds-aceitar" data-i="${i}">Aceitar desafio</button></div></div>`).join('')}</div></div>` : ''}
      ${d.combos.length ? `<div class="cartao"><h2>Criar um desafio</h2>
        <div class="grade g3" style="gap:10px">
          <label class="fraco" style="font-size:13px">Tipo<select class="campo-largo" id="ds-tipo" style="margin-top:4px">${tipoOpts}</select></label>
          <label class="fraco" style="font-size:13px">Carro e pista${seletorCombo(d.combos, chaveCombo(c), 'ds-combo-novo').replace('class="campo-largo"', 'class="campo-largo" id="ds-combo" style="margin-top:4px"')}</label>
          <label class="fraco" style="font-size:13px">Meta<input class="campo-largo" id="ds-alvo" style="margin-top:4px" placeholder="1:41.900 · 5 voltas · 90% · 0,250 s"></label>
        </div>
        <div class="linha" style="margin-top:10px"><button class="btn pri" data-acao="ds-criar">Criar desafio</button><span id="ds-msg" class="fraco"></span></div>
        <p class="fraco" style="font-size:12.5px;margin:8px 0 0">Meta de tempo: escreva como 1:41.900. Voltas seguidas: um número. Voltas válidas: porcentagem. Consistência: a variação máxima em segundos.</p></div>` : ''}`;
  },
  depois() { E._sugestoes = null; api('/api/desafios').then((d) => { E._sugestoes = d.sugestoes; }); },
};
function lerMeta(tipo, txt) {
  txt = (txt || '').trim().replace(',', '.');
  if (tipo === 'tempo') {
    const m = txt.match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
    if (!m) return null;
    return Math.round(((Number(m[1] || 0) * 60) + Number(m[2])) * 1000);
  }
  const n = parseFloat(txt.replace('%', ''));
  if (!isFinite(n) || n <= 0) return null;
  return tipo === 'consistencia' ? Math.round(n * 1000) : n;
}

// ------------------------------------------------------------------ CONFIGURAÇÕES
PAGINAS.config = {
  async html() {
    const c = await api('/api/config');
    return `<div class="linha" style="align-items:flex-end;margin-bottom:16px"><div style="flex:1 1 300px"><h1>Configurações</h1>
        <p class="sub" style="margin:0">Telemetria de cada jogo, inicialização, backup, atalhos e portas.</p></div>
        <button class="btn perigo" data-acao="fechar-app">Fechar o Axtel</button></div>
      <div id="fechar-confirma"></div>
      <div class="cartao"><div class="linha"><h2 style="margin:0">Telemetria dos jogos</h2><span class="esp"></span>
        <button class="btn" data-acao="tele-verificar">Verificar de novo</button></div>
        <p class="fraco" style="margin:6px 0 12px">Mostra se cada jogo está mandando dados para o Axtel e o que ligar dentro do jogo. Quando o jogo deixa, o botão “Ajustar automaticamente” muda o arquivo de configuração por você (com cópia de segurança).</p>
        <div id="tele-lista" class="grade g2"><div class="fraco">Verificando…</div></div></div>
      <div class="grade g2">
        <div class="cartao"><h2>Abrir junto com o Windows</h2>
          <p class="fraco" style="margin:0 0 10px">O Axtel abre minimizado quando o PC liga, pronto para gravar.</p>
          <div class="alternar"><button data-acao="cf-iniciar" data-v="1" class="${c.iniciar_com_windows ? 'on' : ''}">Ligado</button><button data-acao="cf-iniciar" data-v="0" class="${c.iniciar_com_windows ? '' : 'on'}">Desligado</button></div>
          <p id="cf-msg-ini" class="fraco" style="font-size:12.5px"></p></div>
        <div class="cartao"><h2>Backup automático</h2>
          <label class="linha" style="min-height:40px"><input type="checkbox" class="marca" data-mudar="cf-backup" ${c.backup.ativo ? 'checked' : ''}> Fazer um backup por dia do banco</label>
          <label class="fraco" style="font-size:13px">Guardar os últimos
            <select class="campo" data-mudar="cf-manter">${[7, 14, 30, 60].map((n) => `<option ${c.backup.manter === n ? 'selected' : ''}>${n}</option>`).join('')}</select> backups</label>
          <div class="linha" style="margin-top:10px"><button class="btn pri" data-acao="cf-backup-agora">Fazer backup agora</button><span id="cf-msg-bk" class="fraco" style="font-size:12.5px;word-break:break-all"></span></div>
          ${c.backups.length ? `<div style="margin-top:10px">${c.backups.slice(0, 5).map((b) => `<div class="linha fraco" style="font-size:12.5px"><span class="mono">${esc(b.arquivo)}</span><span class="esp"></span>${b.tamanho_kb} KB</div>`).join('')}</div>` : ''}
          <p class="fraco" style="font-size:12.5px;margin:8px 0 0">Pasta: <span class="mono">${esc(c.pasta_dados)}\\backups</span></p></div>
      </div>
      <div class="cartao"><h2>Atalhos do spotter (F9, F10, Ctrl+F10)</h2>
        <p class="fraco" style="margin:0 0 10px">Funcionam com o jogo na frente. Enquanto estiverem ligados, o jogo não recebe essas teclas: se algum comando do jogo usa F9 ou F10, deixe desligado.</p>
        <div class="alternar"><button data-acao="cf-atalhos" data-v="1" class="${c.atalhos ? 'on' : ''}">Ligados</button><button data-acao="cf-atalhos" data-v="0" class="${c.atalhos ? '' : 'on'}">Desligados</button></div>
        <p id="cf-msg-at" class="fraco" style="font-size:12.5px"></p></div>
      <div class="cartao"><h2>Telemetria por rede (F1 25 e Forza)</h2>
        <p class="fraco" style="margin:0 0 10px">No jogo, ligue a telemetria UDP com o IP deste PC (<span class="mono">${esc(E.status ? E.status.ip : '')}</span>) e a mesma porta daqui.</p>
        <div class="grade g2" style="gap:10px">
          <label class="fraco" style="font-size:13px">Porta do F1 25 (padrão 20777)<input class="campo-largo" id="cf-f1" inputmode="numeric" value="${c.portas.f1}" style="margin-top:4px"></label>
          <label class="fraco" style="font-size:13px">Porta do Forza (padrão 5300)<input class="campo-largo" id="cf-forza" inputmode="numeric" value="${c.portas.forza}" style="margin-top:4px"></label>
        </div>
        ${c.portas_em_uso.length ? `<p class="vermelho" style="font-size:13px">Porta ocupada por outro programa: ${esc(c.portas_em_uso.join(', '))}. Escolha outra.</p>` : ''}
        <div class="linha" style="margin-top:10px"><button class="btn pri" data-acao="cf-portas">Salvar portas</button><span id="cf-msg-portas" class="fraco" style="font-size:12.5px"></span></div></div>`;
  },
  depois() {
    desenharTelemetria();
    const t = setInterval(() => { if (!document.querySelector('[data-acao="tele-ajustar"]:disabled')) desenharTelemetria(true); }, 4000);
    E.pararPagina = () => clearInterval(t);
  },
};

async function desenharTelemetria(silencioso) {
  const lista = $('#tele-lista');
  if (!lista) return;
  let d;
  try { d = await api('/api/telemetria'); } catch (e) { if (!silencioso) lista.innerHTML = '<div class="fraco">Não consegui verificar agora.</div>'; return; }
  if (!$('#tele-lista')) return;
  const msgs = {};
  $$('[id^="tele-msg-"]').forEach((m) => { msgs[m.id] = [m.textContent, m.className]; });
  lista.innerHTML = d.jogos.map((j) => {
    const selo = j.nivel === 'ok' ? 'ok' : j.nivel === 'ruim' ? 'ruim' : '';
    const m = msgs['tele-msg-' + j.id] || ['', 'fraco'];
    return `<div class="aviso-item tele-jogo"><div class="linha"><b>${esc(j.nome)}</b><span class="esp"></span>
        ${j.jogo_aberto ? '<span class="selo">jogo aberto</span>' : ''}<span class="selo ${selo}">${j.nivel === 'ok' ? 'recebendo' : j.nivel === 'ruim' ? 'atenção' : 'aguardando'}</span></div>
      <span style="font-size:13px">${esc(j.situacao)}</span>
      ${j.config ? `<span class="fraco" style="font-size:12.5px">Configuração: ${esc(j.config)}${j.arquivo ? ` · <span class="mono" style="word-break:break-all">${esc(j.arquivo)}</span>` : ''}</span>` : ''}
      <ol>${j.passos.map((p) => `<li>${esc(p)}</li>`).join('')}</ol>
      ${j.auto ? `<div class="linha"><button class="btn pri" data-acao="tele-ajustar" data-jogo="${j.id}">Ajustar automaticamente</button></div>` : ''}
      <span id="tele-msg-${j.id}" class="${m[1]}" style="font-size:12.5px">${esc(m[0])}</span></div>`;
  }).join('');
}

// ------------------------------------------------------------------ eventos (cliques e mudanças)
document.addEventListener('click', async (e) => {
  // fecha o painel de status ao clicar fora
  if (E.painelAberto && !e.target.closest('#indicador')) abrirPainel(false);
  const el = e.target.closest('[data-acao]');
  if (!el) {
    const linha = e.target.closest('tr[data-ir]');
    if (linha && !e.target.closest('a,button,input,select,label')) location.hash = linha.dataset.ir;
    return;
  }
  const a = el.dataset.acao;
  const sid = Number(el.dataset.sid);
  switch (a) {
    case 'ind-abrir': abrirPainel(!E.painelAberto); break;
    case 'recarregar': render(false); break;
    case 'voltar': if (history.length > 1 && E.navegou) history.back(); else location.hash = '#/'; break;
    case 'alerta-resolver':
      await post('/api/alerta/resolver', { id: Number(el.dataset.id) });
      await lerStatus();
      break;
    case 'relatorio-enviar': {
      const res = $('#rel-res');
      el.disabled = true;
      res.textContent = 'Salvando…';
      try {
        const r = await post('/api/relatorio', { texto: $('#rel-texto').value });
        res.innerHTML = `Relatório salvo em:<br><span class="mono">${esc(r.arquivo)}</span><br>Mande esse arquivo para analisarmos.`;
        $('#rel-texto').value = '';
      } catch (err) {
        res.textContent = 'Não consegui salvar: o Axtel está aberto?';
      }
      el.disabled = false;
      break;
    }
    case 'volta': alternarVolta(sid, Number(el.dataset.vid)); break;
    case 'sel-melhores': E.sel[sid] = selecaoPadrao(E.sessao.voltas); desenharVoltas(sid); break;
    case 'sel-todas': E.sel[sid].cmp = E.sessao.voltas.filter((v) => v.valida && v.id !== E.sel[sid].ref).map((v) => v.id); desenharVoltas(sid); break;
    case 'sel-limpar': E.sel[sid].cmp = []; desenharVoltas(sid); break;
    case 'combo':
      if (e.target.closest('a')) return;
      E.combo[el.dataset.jogo] = Number(el.dataset.i);
      render(true);
      break;
    case 'apagar': {
      const box = $('#apagar-confirma');
      box.innerHTML = `<div class="aviso" style="margin:12px 0 0">Apagar esta sessão e todas as voltas dela? Isso não pode ser desfeito.
        <div class="linha" style="margin-top:8px"><button class="btn perigo" data-acao="apagar-sim" data-id="${el.dataset.id}">Sim, apagar</button><button class="btn" data-acao="apagar-nao">Cancelar</button></div></div>`;
      break;
    }
    case 'apagar-nao': $('#apagar-confirma').innerHTML = ''; break;
    case 'apagar-sim': {
      const r = await post('/api/sessao/apagar', { id: Number(el.dataset.id) });
      if (r.ok) location.hash = '#/sessoes';
      else $('#apagar-confirma').innerHTML = `<div class="aviso" style="margin:12px 0 0">${esc(r.erro || 'Não foi possível apagar.')}</div>`;
      break;
    }
    case 'replay-play': {
      const R = E.replay;
      if (!R) break;
      const tmax = tmaxCmp();
      if (R.tocando) { R.tocando = false; cancelAnimationFrame(R.raf); } else {
        if (R.t >= tmax) R.t = 0;
        R.tocando = true; R.ult = performance.now(); R.raf = requestAnimationFrame(quadroReplay);
      }
      atualizarReplay();
      break;
    }
    case 'replay-vel':
      if (E.replay) E.replay.vel = Number(el.dataset.v);
      $$('#replay-vel button').forEach((b) => b.classList.toggle('on', b === el));
      break;
    case 'dia':
      if (E.cal) { E.cal.dia = el.dataset.d; desenharResumoDia(true); }
      break;
    case 'pend-add': await adicionarPendencia(); break;
    case 'pend-editar': E.pendEdit = Number(el.dataset.id); E.pendApagar = null; desenharPendencias(); break;
    case 'pend-apagar': E.pendApagar = Number(el.dataset.id); E.pendEdit = null; desenharPendencias(); break;
    case 'pend-cancelar': E.pendEdit = null; E.pendApagar = null; desenharPendencias(); break;
    case 'pend-salvar': {
      const texto = $('#pend-e-texto').value.trim();
      if (!texto) { $('#pend-e-texto').focus(); break; }
      await post('/api/pendencias/editar', { id: Number(el.dataset.id), texto, nota: $('#pend-e-nota').value });
      E.pendEdit = null;
      await recarregarPendencias();
      break;
    }
    case 'pend-apagar-sim':
      await post('/api/pendencias/apagar', { id: Number(el.dataset.id) });
      E.pendApagar = null;
      await recarregarPendencias();
      break;
    case 'pend-ver-feitas': E.verFeitas = !E.verFeitas; desenharPendencias(); break;
    case 'falar-log': { const item = SP.historico[Number(el.dataset.i)]; if (item) falar(item.texto, { forcar: true, registrar: false }); break; }
    case 'liberar-som': {
      liberarSom();
      const aviso = $('#aviso-som');
      aviso.querySelector('span').textContent = 'Som liberado ✓';
      el.hidden = true;
      falar(SP.ultimo || 'Som liberado.', { forcar: true, registrar: false });
      setTimeout(() => { aviso.hidden = true; aviso.querySelector('span').textContent = 'O navegador bloqueou o som do spotter.'; el.hidden = false; }, 2500);
      break;
    }
    case 'sp-repetir': if (SP.ultimo) falar(SP.ultimo, { forcar: true, registrar: false }); else falar(fraseExemplo('tempo', spLingua()), { forcar: true, registrar: false }); break;
    case 'sp-silenciar': spComando('silenciar'); break;
    case 'sp-ligar': spSalvar({ ligado: !SP.cfg.ligado }); render(true); break;
    case 'sp-op': spSalvar({ [el.dataset.campo]: el.dataset.v }); render(true); break;
    case 'sp-testar': {
      const l = spLingua();
      falar({ pt: 'Aqui é o Beto, seu spotter. Rádio testado, pode acelerar.', en: 'Spotter here. Radio check done, you are good to go.', es: 'Aquí tu spotter. Radio probada, puedes acelerar.' }[l], { forcar: true, tipo: 'teste' });
      break;
    }
    case 'sp-exemplo': falar(fraseExemplo(el.dataset.id, spLingua()), { forcar: true, registrar: false }); break;
    case 'cmp-info': { const inf = cmpInfo(); inf[el.dataset.k] = !inf[el.dataset.k]; guardar('axtel.comparar.info', inf); render(true); break; }
    case 'cmp-todas': E.cmpOcultas = []; render(true); break;
    case 'cmp-nenhuma': E.cmpOcultas = E.cmp.voltas.slice(1).map((v) => v.id); render(true); break;
    case 'cmp-ref': { const ids = E.cmp.voltas.map((v) => v.id), id = Number(el.dataset.id); irComparar([id].concat(ids.filter((x) => x !== id))); break; }
    case 'cmp-tirar': { const id = Number(el.dataset.id); irComparar(E.cmp.voltas.map((v) => v.id).filter((x) => x !== id)); break; }
    case 'cal-destacar': E.calDestacar = E.calDestacar === false; render(true); break;
    case 'st-salvar': {
      const c = E.combo_setup;
      const r = await post('/api/setups/salvar', { id: el.dataset.id || null, jogo: c.jogo, carro: c.carro, pista: c.pista,
        nome: $('#st-nome').value, parametros_texto: $('#st-params').value, notas: $('#st-notas').value });
      if (!r.ok) { $('#st-msg').textContent = r.erro; break; }
      E.setupEditar = null; render(true); break;
    }
    case 'st-cancelar': E.setupEditar = null; render(true); break;
    case 'st-editar': E.setupEditar = Number(el.dataset.id); await render(true); $('#form-setup').scrollIntoView({ behavior: 'smooth' }); break;
    case 'st-apagar': {
      if (el.dataset.confirma !== '1') { el.dataset.confirma = '1'; el.textContent = 'Clique de novo para apagar'; break; }
      await post('/api/setups/apagar', { id: Number(el.dataset.id) }); render(true); break;
    }
    case 'st-comp-limpar': E.setupComparar = []; render(true); break;
    case 'ds-apagar': {
      if (el.dataset.confirma !== '1') { el.dataset.confirma = '1'; el.textContent = 'Confirmar'; break; }
      await post('/api/desafios/apagar', { id: Number(el.dataset.id) }); render(true); break;
    }
    case 'ds-ver-feitos': E.verDesafiosFeitos = !E.verDesafiosFeitos; render(true); break;
    case 'ds-aceitar': {
      const d = await api('/api/desafios');
      const sg = d.sugestoes[Number(el.dataset.i)];
      if (sg) await post('/api/desafios/criar', sg);
      render(true); break;
    }
    case 'ds-criar': {
      const tipo = $('#ds-tipo').value;
      const [jogo, carro, pista] = $('#ds-combo').value.split('|');
      const alvo = lerMeta(tipo, $('#ds-alvo').value);
      if (alvo == null) { $('#ds-msg').textContent = 'Meta inválida. Veja os exemplos abaixo.'; break; }
      const r = await post('/api/desafios/criar', { tipo, jogo, carro, pista, alvo });
      if (!r.ok) { $('#ds-msg').textContent = r.erro; break; }
      render(true); break;
    }
    case 'cf-iniciar': {
      const r = await post('/api/config', { iniciar_com_windows: el.dataset.v === '1' });
      $$('[data-acao="cf-iniciar"]').forEach((b) => b.classList.toggle('on', r.ok ? b === el : !b.classList.contains('on')));
      $('#cf-msg-ini').textContent = r.ok ? r.aviso : r.erro; break;
    }
    case 'fechar-app':
      $('#fechar-confirma').innerHTML = `<div class="aviso">Fechar o Axtel? A gravação para até você abrir de novo pelo atalho. A sessão em andamento fica salva.
        <div class="linha" style="margin-top:8px"><button class="btn perigo" data-acao="fechar-sim">Sim, fechar</button><button class="btn" data-acao="fechar-nao">Cancelar</button></div></div>`;
      break;
    case 'fechar-nao': $('#fechar-confirma').innerHTML = ''; break;
    case 'vivo-janela': {
      const w = window.open(location.pathname + '#/aovivo?janela=1', NOME_JANELA_VIVO,
        'popup=yes,width=1280,height=760,menubar=no,toolbar=no,location=no,status=no');
      if (!w) { alert('O navegador bloqueou a janela. Permita pop-ups para o Axtel e tente de novo.'); break; }
      w.focus(); break;
    }
    case 'vivo-tela-cheia':
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen().catch(() => {});
      break;
    case 'tele-verificar': desenharTelemetria(); break;
    case 'tele-ajustar': {
      el.disabled = true;
      const r = await post('/api/telemetria/ajustar', { jogo: el.dataset.jogo });
      el.disabled = false;
      await desenharTelemetria();
      const m = $('#tele-msg-' + el.dataset.jogo);
      if (m) { m.textContent = r.ok ? r.aviso : r.erro; m.className = r.ok ? 'verde' : 'vermelho'; }
      break;
    }
    case 'fechar-sim':
      await post('/api/fechar');
      document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;text-align:center;font:16px system-ui;color:#E7EAEE;background:#0D1015"><div><h1>Axtel fechado</h1><p style="color:#8C95A2">Para abrir de novo, use o atalho Axtel na área de trabalho.</p></div></div>';
      break;
    case 'cf-atalhos': {
      const r = await post('/api/config', { atalhos: el.dataset.v === '1' });
      $$('[data-acao="cf-atalhos"]').forEach((b) => b.classList.toggle('on', b === el));
      $('#cf-msg-at').textContent = r.ok ? r.aviso : r.erro; break;
    }
    case 'cf-backup-agora': {
      el.disabled = true;
      const r = await post('/api/backup');
      $('#cf-msg-bk').textContent = r.ok ? 'Backup salvo: ' + r.arquivo : (r.erro || 'Não consegui fazer o backup.');
      el.disabled = false; break;
    }
    case 'cf-portas': {
      const r = await post('/api/config', { portas: { f1: $('#cf-f1').value, forza: $('#cf-forza').value } });
      $('#cf-msg-portas').textContent = r.ok ? r.aviso : r.erro; break;
    }
    default: break;
  }
});

document.addEventListener('change', (e) => {
  const el = e.target.closest('[data-mudar]');
  if (!el) return;
  switch (el.dataset.mudar) {
    case 'volta': alternarVolta(Number(el.dataset.sid), Number(el.dataset.vid)); break;
    case 'ref': virarRef(Number(el.dataset.sid), Number(el.dataset.vid)); break;
    case 'cmp-mostrar': {
      const id = Number(el.dataset.id);
      E.cmpOcultas = (E.cmpOcultas || []).filter((x) => x !== id);
      if (!el.checked) E.cmpOcultas.push(id);
      render(true); break;
    }
    case 'cmp-add': if (el.value) irComparar(E.cmp.voltas.map((v) => v.id).concat([Number(el.value)])); break;
    case 'sessao-setup': {
      post('/api/sessao/setup', { sessao_id: Number(el.dataset.sid), setup_id: el.value || null })
        .then(() => { const m = $('#setup-msg'); if (m) m.textContent = 'Setup salvo nesta sessão.'; });
      break;
    }
    case 'st-combo': guardar('axtel.combo', el.value); E.setupEditar = null; E.setupComparar = []; location.hash = '#/setups?combo=' + enc(el.value); break;
    case 'ds-combo': guardar('axtel.combo', el.value); location.hash = '#/desafios?combo=' + enc(el.value); break;
    case 'st-comp': {
      const id = Number(el.dataset.id);
      E.setupComparar = (E.setupComparar || []).filter((x) => x !== id);
      if (el.checked) { E.setupComparar.push(id); if (E.setupComparar.length > 2) E.setupComparar.shift(); }
      render(true); break;
    }
    case 'sp-chk': spSalvar({ [el.dataset.campo]: el.checked }); break;
    case 'sp-num': spSalvar({ [el.dataset.campo]: Number(el.value) }); break;
    case 'sp-sel': spSalvar({ [el.dataset.campo]: el.dataset.campo === 'intervalo' ? Number(el.value) : el.value }); render(true); break;
    case 'sp-voz': {
      const vz = SP.cfg.vozes || {};
      vz[el.dataset.l] = Object.assign({}, vz[el.dataset.l], { [el.dataset.campo]: el.value.trim() });
      spSalvar({ vozes: vz }); break;
    }
    case 'sp-voz-nav': guardar('axtel.voz.navegador.' + spLingua(), el.value); falar({ pt: 'Pronto. Essa é a voz escolhida.', en: 'Done. This is the voice you picked.', es: 'Listo. Esta es la voz elegida.' }[spLingua()], { forcar: true, registrar: false }); break;
    case 'sp-aviso': {
      const id = el.dataset.id, d = (SP.cfg.desligados || []).filter((x) => x !== id);
      const a = AVISOS.find((x) => x[0] === id);
      const letra = SP.cfg.modo === 'silencioso' ? 's' : SP.cfg.modo === 'falador' ? 'f' : 'n';
      const mud = { desligados: el.checked ? d : d.concat([id]) };
      if (el.checked && !a[3].includes(letra)) mud.modo = 'falador';
      spSalvar(mud); render(true); break;
    }
    case 'cf-backup': post('/api/config', { backup: { ativo: el.checked } }); break;
    case 'cf-manter': post('/api/config', { backup: { manter: Number(el.value) } }); break;
    case 'tipo': {
      const p = new URLSearchParams();
      if (el.dataset.jogo) p.set('jogo', el.dataset.jogo);
      if (el.value) p.set('tipo', el.value);
      if (el.dataset.data) p.set('data', el.dataset.data);
      location.hash = '#/sessoes' + (p.toString() ? '?' + p : '');
      break;
    }
    case 'pend-feita':
      post('/api/pendencias/editar', { id: Number(el.dataset.id), feita: el.checked }).then(recarregarPendencias);
      break;
    default: break;
  }
});

document.addEventListener('input', (e) => {
  if (e.target.dataset && e.target.dataset.mudar === 'sp-num') {
    const v = Number(e.target.value);
    if (e.target.dataset.campo === 'volume' && $('#sp-vol-txt')) $('#sp-vol-txt').textContent = v + '%';
    if (e.target.dataset.campo === 'ritmo' && $('#sp-rit-txt')) $('#sp-rit-txt').textContent = (v / 100).toFixed(2).replace('.', ',') + '×';
  }
  if (e.target.id === 'replay-pos' && E.replay && E.cmp) {
    const tmax = tmaxCmp();
    E.replay.t = (Number(e.target.value) / 1000) * tmax;
    atualizarReplay();
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && E.painelAberto) abrirPainel(false);
  if (e.key === 'Enter' && e.target.id === 'pend-texto') { e.preventDefault(); adicionarPendencia(); }
  if (e.key === 'Enter' && e.target.id === 'pend-e-texto') { e.preventDefault(); const b = $('[data-acao="pend-salvar"]'); if (b) b.click(); }
  if (e.key === 'Escape' && (E.pendEdit || E.pendApagar)) { E.pendEdit = null; E.pendApagar = null; desenharPendencias(); }
});

// ------------------------------------------------------------------ início
const NOME_JANELA_VIVO = 'axtel_aovivo';
if (window.name === NOME_JANELA_VIVO || lerRota().q.janela === '1') {
  window.name = NOME_JANELA_VIVO;
  document.body.classList.add('janela');
  document.title = 'Axtel · Ao vivo';
}
carregarSpotter().then(lerStatus).then(() => render(false));
api('/api/pendencias').then((d) => atualizarNavPend(d.pendencias)).catch(() => {});
setInterval(lerStatus, 1500);
