"""Validação completa do Axtel.

1. Simulação: sobe o Axtel com o simulador e roda os 7 jogos (AC EVO, Assetto Corsa, iRacing, Automobilista 2, F1 25, Forza)
   conferindo que cada um gera sessão e que a tela Ao vivo recebe os dados.
2. Roteiro (Playwright): abre cada tela e clica em cada botão conferindo o resultado. No PC e num celular simulado.
3. Macaco (gremlins.js): centenas de cliques e digitação aleatórios em cada tela.
4. Varredura (no estilo do buttonmash): acha e clica em todos os botões, links, caixas e seletores de cada tela.

Uso: python validar.py            (gera relatorio/index.html)
"""
import base64
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import sync_playwright, expect

AQUI = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(AQUI, "simulador.py")
PORTA = int(os.environ.get("AXTEL_PORTA_TESTE", "8611"))
BASE = f"http://localhost:{PORTA}"
REL = os.path.join(AQUI, "relatorio")
DADOS = os.path.join(AQUI, ".dados-teste")
GREMLINS = os.path.join(AQUI, "vendor", "gremlins")
PERIGOSOS = ("fechar-app", "fechar-sim", "apagar", "apagar-sim", "pend-apagar", "pend-apagar-sim", "st-apagar", "ds-apagar", "cf-iniciar", "cf-atalhos")
TELAS = [("Início", "#/", "Início"), ("Estatísticas por jogo", "#/jogo", "Estatísticas por jogo"), ("Sessões", "#/sessoes", "Sessões"),
         ("Calendário", "#/calendario", "Calendário"), ("Setups", "#/setups", "Setups"), ("Desafios e plano", "#/desafios", "Desafios e plano"),
         ("Anotações", "#/anotacoes", "Anotações"), ("Ao vivo", "#/aovivo", "Ao vivo"), ("Spotter", "#/spotter", "Spotter"),
         ("Configurações", "#/config", "Configurações")]
JOGOS = ["AC EVO", "Assetto Corsa", "iRacing", "Automobilista 2", "F1 25", "Forza"]

resultados = []  # (grupo, nome, ok, detalhe, print)


def api(caminho):
    with urllib.request.urlopen(BASE + caminho, timeout=5) as r:
        return json.loads(r.read())


def registrar(grupo, nome, ok, detalhe="", foto=None):
    resultados.append((grupo, nome, ok, detalhe, foto))
    print(("OK    " if ok else "FALHA ") + f"[{grupo}] {nome}" + (f" — {detalhe}" if detalhe and not ok else ""), flush=True)


def caso(grupo, nome, pagina=None):
    def deco(f):
        def rodar(*a):
            erros = []
            if pagina is not None:
                pagina.on("pageerror", lambda e: erros.append("erro: " + str(e)[:300]))
            foto = None
            try:
                f(*a)
                ok, det = not erros, "; ".join(erros[:3])
            except Exception as e:
                ok, det = False, f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
            if pagina is not None:
                foto = os.path.join("telas", re.sub(r"[^a-z0-9]+", "-", (grupo + " " + nome).lower()).strip("-") + ".png")
                try:
                    pagina.screenshot(path=os.path.join(REL, foto), full_page=False)
                except Exception:
                    foto = None
            registrar(grupo, nome, ok, det, foto)
        return rodar
    return deco


# ------------------------------------------------------------------ 1. simulação
def foto_ao_vivo():
    """Abre a tela Ao vivo com o AC EVO simulado rodando e confere os cartões novos."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(BASE + "/#/aovivo")
            pg.locator("#v-mapa-eu").wait_for(timeout=15000)
            pg.wait_for_timeout(800)
            r = {"volante": pg.locator("#v-vol-txt").inner_text(), "pneu": pg.locator("#v-pt0").inner_text(),
                 "posicao": pg.locator("#v-posicao").inner_text(), "rpm": pg.locator("#v-rpm-txt").inner_text(),
                 "comb": pg.locator("#v-cpv").inner_text(), "outros": pg.locator("#v-mapa-outros circle").count()}
            os.makedirs(os.path.join(REL, "telas"), exist_ok=True)
            pg.screenshot(path=os.path.join(REL, "telas", "ao-vivo-com-jogo.png"), full_page=True)
            nav.close()
            return r
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {e}"}


def simulacao():
    shutil.rmtree(DADOS, ignore_errors=True)
    os.makedirs(DADOS)
    log = open(os.path.join(REL, "simulador.log"), "w")
    proc = subprocess.Popen([sys.executable, SIM, DADOS, str(PORTA)], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            api("/api/status")
            break
        except Exception:
            time.sleep(0.5)
    vistos = {}
    fim = time.time() + 600
    while time.time() < fim:
        try:
            v = api("/api/aovivo")
            if v.get("jogo"):
                d = vistos.setdefault(v["jogo"], {"amostras": 0, "tempos": set(), "carro": v["carro"], "pista": v["pista"]})
                d["amostras"] += 1
                d["tempos"].add(v["atual_ms"])
                d.setdefault("info", set()).update((v.get("info") or {}).keys())
                if v["jogo"] == "AC EVO" and ((v.get("info") or {}).get("mapa") or {}).get("completo") and "tela_vivo" not in d:
                    d["tela_vivo"] = foto_ao_vivo()
        except Exception:
            pass
        if "simulação terminada" in open(os.path.join(REL, "simulador.log")).read():
            break
        time.sleep(0.5)
    ss = api("/api/sessoes")["sessoes"]
    tv = (vistos.get("AC EVO") or {}).get("tela_vivo") or {}
    ok_tv = ("°" in tv.get("volante", "") and tv.get("pneu") == "86°" and tv.get("posicao", "").startswith("P4")
             and "9.250" in tv.get("rpm", "") and tv.get("comb", "").startswith("2,9") and tv.get("outros") == 2)
    registrar("Jogos", "AC EVO: Ao vivo mostra volante, pneus, motor, combustível e mapa", ok_tv, json.dumps(tv, ensure_ascii=False),
              "telas/ao-vivo-com-jogo.png" if os.path.exists(os.path.join(REL, "telas", "ao-vivo-com-jogo.png")) else None)
    for j, chaves in (("iRacing", {"posicao", "agua"}), ("Automobilista 2", {"volante", "rpm_max", "posicao"}),
                      ("F1 25", {"volante", "pneus_temp", "posicao"}), ("Forza", {"volante", "rpm_max"})):
        tem = (vistos.get(j) or {}).get("info", set())
        registrar("Jogos", f"{j}: Ao vivo recebe os dados extras", chaves <= tem, f"faltou: {sorted(chaves - tem)}")
    sac = [s for s in ss if s["jogo"] == "Assetto Corsa"]
    registrar("Jogos", "Assetto Corsa: repique do tempo na linha não invalida a volta seguinte",
              bool(sac) and sac[0]["validas"] >= sac[0]["voltas"] - 2,
              f"{sac[0]['voltas']} voltas, {sac[0]['validas']} válidas" if sac else "sem sessão")
    for j in JOGOS:
        sj = [s for s in ss if s["jogo"] == j]
        v = vistos.get(j)
        registrar("Jogos", f"{j}: Ao vivo recebe os dados", bool(v and len(v["tempos"]) > 5),
                  "" if v else "a tela Ao vivo nunca mostrou este jogo")
        ok = bool(sj) and sj[0]["voltas"] >= 3 and sj[0]["validas"] >= 1 and sj[0]["melhor_ms"]
        det = (f"{sj[0]['carro']} · {sj[0]['pista']} · {sj[0]['voltas']} voltas, {sj[0]['validas']} válidas, melhor {sj[0]['melhor_ms']} ms"
               if sj else "nenhuma sessão gravada")
        registrar("Jogos", f"{j}: grava sessão e voltas", ok, det)
        if sj and j == "Forza":
            registrar("Jogos", "Forza: não informa volta inválida (limitação do jogo, já documentada)", True)
        elif sj:
            vs = api(f"/api/sessao?id={sj[0]['id']}")["voltas"]
            inval = [v for v in vs if not v["valida"] and v["numero"] > 1]
            registrar("Jogos", f"{j}: volta com corte vira inválida", bool(inval),
                      "; ".join(f"volta {v['numero']}: {v['motivo']}" for v in inval) or "nenhuma volta inválida além da saída")
    return proc


# ------------------------------------------------------------------ 2. roteiro
def roteiro(ctx, celular=False):
    pg = ctx.new_page()
    G = "Roteiro celular" if celular else "Roteiro PC"

    def abrir(rota):
        pg.goto(BASE + "/" + rota)
        pg.locator("main h1").first.wait_for(timeout=15000)

    if celular:
        for nome, rota, _ in TELAS:
            @caso(G, f"{nome}: sem rolagem lateral", pg)
            def _():
                abrir(rota)
                pg.wait_for_timeout(400)
                w = pg.evaluate("document.documentElement.scrollWidth")
                assert w <= pg.viewport_size["width"] + 2, f"página com {w}px numa tela de {pg.viewport_size['width']}px"
            _()
        pg.close()
        return

    @caso(G, "Menu: cada item abre a tela certa", pg)
    def _():
        abrir("#/")
        for nome, rota, titulo in TELAS:
            pg.locator("#nav a", has_text=nome).first.click()
            expect(pg.locator("main h1").first).to_contain_text(titulo, timeout=10000)
            pg.screenshot(path=os.path.join(REL, "telas", "tela-" + re.sub(r"[^a-z0-9]+", "-", nome.lower()) + ".png"), full_page=True)
    _()

    @caso(G, "Barra lateral fixa: só o conteúdo rola", pg)
    def _():
        abrir("#/sessoes")
        antes = pg.locator(".side").bounding_box()
        pg.locator("main").evaluate("m => m.scrollTo(0, 3000)")
        pg.wait_for_timeout(200)
        assert pg.locator(".side").bounding_box() == antes, "a barra lateral se moveu"
    _()

    @caso(G, "Atalho do Spotter na lateral", pg)
    def _():
        abrir("#/")
        pg.click("#atalho-spotter")
        expect(pg.locator("main h1").first).to_contain_text("Spotter")
    _()

    @caso(G, "Botão Voltar", pg)
    def _():
        abrir("#/sessoes")
        pg.locator("main a.btn", has_text="Abrir").first.click()
        pg.locator("#cartao-voltas table").first.wait_for()
        pg.click('[data-acao="voltar"]')
        expect(pg).to_have_url(re.compile(r"#/sessoes"))
    _()

    @caso(G, "Início: escolher jogo abre as estatísticas dele", pg)
    def _():
        abrir("#/")
        pg.locator(".escolha a.chip", has_text="iRacing").first.click()
        expect(pg.locator("main")).to_contain_text("Mazda MX-5 Cup")
    _()

    @caso(G, "Estatísticas: trocar jogo e combinação", pg)
    def _():
        abrir("#/jogo")
        for j in JOGOS:
            pg.locator(".escolha a.chip", has_text=j).first.click()
            pg.wait_for_timeout(300)
            expect(pg.locator("main")).to_contain_text("Carros e pistas")
        pg.locator('tr[data-acao="combo"]').first.click()
    _()

    @caso(G, "Sessões: filtro por jogo, tipo e linha clicável", pg)
    def _():
        abrir("#/sessoes")
        total = pg.locator("main tbody tr").count()
        pg.locator(".chips a.chip", has_text="F1 25").first.click()
        expect(pg.locator("main tbody tr")).to_have_count(1)
        pg.locator(".chips a.chip", has_text="Todos").first.click()
        expect(pg.locator("main tbody tr")).to_have_count(total)
        pg.select_option("#filtro-tipo", index=1)
        expect(pg).to_have_url(re.compile("tipo="))
        pg.locator("main tbody tr").first.locator("td").nth(2).click()
        pg.locator("#cartao-voltas").wait_for()
    _()

    @caso(G, "Detalhe: REF, várias voltas, botões e CSV", pg)
    def _():
        abrir("#/sessoes")
        pg.locator("main tbody tr", has_text="Porsche").locator("a.btn", has_text="Abrir").first.click()
        pg.locator("#cartao-voltas table").first.wait_for()
        pg.click('[data-acao="sel-limpar"]')
        expect(pg.locator('input[data-mudar="volta"]:checked')).to_have_count(0)
        pg.locator('input[data-mudar="ref"]').nth(2).check()
        expect(pg.locator(".tag-sel.ref").first).to_be_visible()
        livres = pg.locator('input[data-mudar="volta"]:not([disabled])')
        livres.nth(0).check()
        livres.nth(3).check()
        expect(pg.locator('input[data-mudar="volta"]:checked')).to_have_count(2)
        expect(pg.locator(".cmp table tbody tr")).to_have_count(2)
        pg.click('[data-acao="sel-todas"]')
        assert pg.locator('input[data-mudar="volta"]:checked').count() >= 3, "Todas as válidas marcou menos de 3"
        pg.click('[data-acao="sel-melhores"]')
        expect(pg.locator('input[data-mudar="volta"]:checked')).to_have_count(1)
        pg.locator(".grafico-voltas button").last.click()
        pg.click('[data-acao="apagar"]')
        pg.click('[data-acao="apagar-nao"]')
        with pg.expect_download() as d:
            pg.click("text=Baixar voltas")
        assert d.value.suggested_filename.endswith(".csv")
    _()

    @caso(G, "Detalhe: escolher o setup usado", pg)
    def _():
        abrir("#/setups")
        pg.fill("#st-nome", "Setup do teste")
        pg.fill("#st-params", "Asa traseira = 6\nTC = 2")
        pg.click('[data-acao="st-salvar"]')
        expect(pg.locator("main")).to_contain_text("Setup do teste")
        combo = pg.locator('select[data-mudar="st-combo"] option:checked').inner_text()
        abrir("#/sessoes")
        carro = combo.split(" · ")[0]
        pg.locator("main tbody tr", has_text=carro).locator("a.btn", has_text="Abrir").first.click()
        pg.locator('select[data-mudar="sessao-setup"]').select_option(label="Setup do teste")
        expect(pg.locator("#setup-msg")).to_contain_text("salvo")
    _()

    @caso(G, "Comparar: cores, mostrar/ocultar, REF, adicionar, tirar, replay", pg)
    def _():
        abrir("#/sessoes")
        pg.locator("main tbody tr", has_text="Porsche").locator("a.btn", has_text="Abrir").first.click()
        pg.locator("#cartao-voltas table").first.wait_for()
        pg.click('[data-acao="sel-todas"]')
        pg.locator(".cmp a.btn.pri").click()
        expect(pg.locator("main h1").first).to_contain_text("Comparar voltas")
        n = pg.locator('input[data-mudar="cmp-mostrar"]').count()
        assert n >= 3, f"só {n} voltas na comparação"
        cores = pg.locator("main table tbody tr td:nth-child(2) span").evaluate_all("els => els.map(e => getComputedStyle(e).borderTopColor)")
        assert len(set(cores)) == len(cores), "voltas com a mesma cor"
        for b in pg.locator('[data-acao="cmp-info"]').all():
            b.click()
        expect(pg.locator("main")).to_contain_text("Todas as informações estão ocultas")
        for b in pg.locator('[data-acao="cmp-info"]').all():
            b.click()
        pg.locator('input[data-mudar="cmp-mostrar"]:not([disabled])').first.uncheck()
        pg.click('[data-acao="cmp-todas"]')
        pg.click('[data-acao="cmp-nenhuma"]')
        pg.click('[data-acao="cmp-todas"]')
        def espera_tela(url_antes):
            pg.wait_for_function("u => location.href !== u", arg=url_antes)
            pg.wait_for_function("() => typeof E !== 'undefined' && E.replay && document.querySelector('#replay-play')")
            pg.wait_for_timeout(300)
        u = pg.url; pg.locator('[data-acao="cmp-ref"]').first.click(); espera_tela(u)
        u = pg.url; pg.locator('[data-acao="cmp-tirar"]').first.click(); espera_tela(u)
        if pg.locator("#cmp-add").count():
            u = pg.url; pg.locator("#cmp-add").select_option(index=1); espera_tela(u)
        pg.click("#replay-play")
        pg.wait_for_timeout(900)
        assert pg.locator("#rp-t").inner_text() != "0:00.000", "o replay não andou"
        pg.locator("#replay-pos").fill("600")
        assert pg.locator("#rp-voltas .linha").count() >= 2, "o replay não mostra as voltas"
    _()

    @caso(G, "Calendário: dia, resumo, destaque de melhora, filtro e meses", pg)
    def _():
        abrir("#/calendario")
        pg.locator(".dia[data-d]").nth(3).click()
        pg.locator("#resumo-dia .cartao").wait_for()
        dias = pg.locator(".dia .info").count()
        assert dias > 0, "nenhum dia com corrida no mês"
        pg.locator(".dia[data-d]", has=pg.locator(".info")).first.click()
        expect(pg.locator("#resumo-dia")).to_contain_text("Abrir sessão")
        pg.click('[data-acao="cal-destacar"]')
        pg.click('[data-acao="cal-destacar"]')
        pg.locator(".chips a.chip", has_text="Forza").first.click()
        pg.locator(".cal-topo a.btn").first.click()
        pg.locator(".cal-topo a.btn").nth(1).click()
        pg.locator("#resumo-dia a.btn", has_text="Sessões").first.click() if pg.locator("#resumo-dia a.btn", has_text="Sessões").count() else None
    _()

    @caso(G, "Setups: criar dois, comparar, editar, apagar", pg)
    def _():
        abrir("#/setups")
        for nome in ("Seco A", "Seco B"):
            pg.fill("#st-nome", nome)
            pg.fill("#st-params", "Asa traseira = 6\nFreio = 55%" if nome.endswith("A") else "Asa traseira = 8\nFreio = 57%")
            pg.click('[data-acao="st-salvar"]')
            expect(pg.locator("main")).to_contain_text(nome)
        cx = pg.locator('input[data-mudar="st-comp"]')
        cx.nth(0).check()
        pg.locator('input[data-mudar="st-comp"]').nth(1).check()
        expect(pg.locator("main")).to_contain_text("mudou")
        pg.click('[data-acao="st-comp-limpar"]')
        pg.locator('[data-acao="st-editar"]').first.click()
        expect(pg.locator('[data-acao="st-cancelar"]')).to_be_visible()
        expect(pg.locator("#st-nome")).not_to_have_value("")
        pg.fill("#st-nome", "Seco B editado")
        pg.locator('[data-acao="st-salvar"]').click()
        expect(pg.locator("main")).to_contain_text("Seco B editado")
        antes = pg.locator('[data-acao="st-apagar"]').count()
        pg.locator('[data-acao="st-apagar"]').first.click()
        pg.locator('[data-acao="st-apagar"]').first.click()
        expect(pg.locator('[data-acao="st-apagar"]')).to_have_count(antes - 1)
    _()

    @caso(G, "Desafios: plano, sugestão, criar, concluídos, apagar", pg)
    def _():
        abrir("#/desafios")
        expect(pg.locator("main")).to_contain_text("Plano de treino")
        pg.locator('select[data-mudar="ds-combo"]').select_option(index=1)
        pg.locator("main h1").first.wait_for()
        sug = pg.locator('[data-acao="ds-aceitar"]')
        if sug.count():
            sug.first.click()
            pg.wait_for_timeout(400)
        pg.select_option("#ds-tipo", "seguidas")
        pg.fill("#ds-alvo", "2")
        pg.click('[data-acao="ds-criar"]')
        expect(pg.locator("main")).to_contain_text("2 voltas válidas seguidas")
        pg.select_option("#ds-tipo", "tempo")
        pg.fill("#ds-alvo", "abc")
        pg.click('[data-acao="ds-criar"]')
        expect(pg.locator("#ds-msg")).to_contain_text("inválida")
        if pg.locator('[data-acao="ds-ver-feitos"]').count():
            pg.click('[data-acao="ds-ver-feitos"]')
        antes = pg.locator('[data-acao="ds-apagar"]').count()
        pg.locator('[data-acao="ds-apagar"]').first.click()
        pg.locator('[data-acao="ds-apagar"]').first.click()
        expect(pg.locator('[data-acao="ds-apagar"]')).to_have_count(antes - 1)
    _()

    @caso(G, "Anotações: começa vazia, adicionar, editar, concluir, apagar", pg)
    def _():
        abrir("#/anotacoes")
        expect(pg.locator("#pend-lista")).to_contain_text("Nenhuma anotação aberta")
        pg.fill("#pend-texto", "Anotação de teste")
        pg.keyboard.press("Enter")
        expect(pg.locator("#pend-lista")).to_contain_text("Anotação de teste")
        expect(pg.locator("#nav-pend")).to_have_text("1")
        pg.click('[data-acao="pend-add"]')
        expect(pg.locator("#pend-msg")).to_contain_text("Escreva")
        pg.locator('[data-acao="pend-editar"]').first.click()
        pg.fill("#pend-e-texto", "Anotação editada")
        pg.locator('[data-acao="pend-salvar"]').click()
        expect(pg.locator("#pend-lista")).to_contain_text("Anotação editada")
        pg.locator('input[data-mudar="pend-feita"]').first.check()
        pg.wait_for_timeout(300)
        pg.click('[data-acao="pend-ver-feitas"]')
        pg.locator('[data-acao="pend-apagar"]').first.click()
        pg.click('[data-acao="pend-apagar-sim"]')
        expect(pg.locator("#pend-lista")).not_to_contain_text("Anotação editada")
    _()

    @caso(G, "Spotter: todos os controles e salvamento", pg)
    def _():
        abrir("#/spotter")
        pg.click('[data-acao="sp-ligar"]')
        expect(pg.locator("#spot-estado")).to_have_text("desligado")
        pg.click('[data-acao="sp-ligar"]')
        expect(pg.locator("#spot-estado")).to_have_text("ligado")
        for k in range(pg.locator('[data-acao="sp-op"]').count()):
            pg.locator('[data-acao="sp-op"]').nth(k).click()
        for k in range(pg.locator('input[data-mudar="sp-aviso"]').count()):
            pg.locator('input[data-mudar="sp-aviso"]').nth(k).click()
        for k in range(pg.locator('input[data-mudar="sp-chk"]').count()):
            pg.locator('input[data-mudar="sp-chk"]').nth(k).click()
            pg.locator('input[data-mudar="sp-chk"]').nth(k).click()
        pg.locator('select[data-mudar="sp-sel"][data-campo="intervalo"]').select_option("8")
        pg.locator('input[data-mudar="sp-num"]').first.fill("60")
        pg.locator('input[data-mudar="sp-num"]').first.dispatch_event("change")
        pg.locator('input[data-mudar="sp-voz"][data-l="en"][data-campo="id"]').fill("idTesteIngles")
        pg.locator('input[data-mudar="sp-voz"][data-l="en"][data-campo="id"]').dispatch_event("change")
        pg.click('[data-acao="sp-testar"]')
        pg.locator('[data-acao="sp-exemplo"]').first.click()
        pg.click('[data-acao="sp-repetir"]')
        pg.click('[data-acao="sp-silenciar"]')
        expect(pg.locator("#spot-estado")).to_have_text("em silêncio")
        pg.wait_for_timeout(800)
        sp = api("/api/config")["spotter"]
        assert sp["volume"] == 60 and sp["intervalo"] == 8 and sp["vozes"]["en"]["id"] == "idTesteIngles", f"não salvou: {sp}"
        assert sp["vozes"]["pt"]["id"] == "xNGAXaCH8MaasNuo7Hr7", "a voz Beto foi alterada"
    _()

    @caso(G, "Configurações: backup, portas e alternâncias", pg)
    def _():
        abrir("#/config")
        pg.click('[data-acao="cf-backup-agora"]')
        expect(pg.locator("#cf-msg-bk")).to_contain_text("Backup salvo")
        pg.fill("#cf-f1", "99")
        pg.click('[data-acao="cf-portas"]')
        expect(pg.locator("#cf-msg-portas")).to_contain_text("inválida")
        pg.fill("#cf-f1", "20777")
        pg.click('[data-acao="cf-portas"]')
        expect(pg.locator("#cf-msg-portas")).to_contain_text("aberto de novo")
        pg.locator('input[data-mudar="cf-backup"]').click()
        pg.locator('input[data-mudar="cf-backup"]').click()
        pg.locator('select[data-mudar="cf-manter"]').select_option("30")
        pg.locator('[data-acao="cf-atalhos"][data-v="1"]').click()
        expect(pg.locator("#cf-msg-at")).to_contain_text("aberto de novo")
        pg.locator('[data-acao="cf-atalhos"][data-v="0"]').click()
    _()

    @caso(G, "Configurações: telemetria dos jogos", pg)
    def _():
        abrir("#/config")
        expect(pg.locator("#tele-lista .tele-jogo")).to_have_count(6)
        expect(pg.locator("#tele-lista")).to_contain_text("Project CARS 2")
        expect(pg.locator('[data-acao="tele-ajustar"]')).to_have_count(2)
        pg.click('[data-acao="tele-ajustar"][data-jogo="iracing"]')
        expect(pg.locator("#tele-msg-iracing")).not_to_be_empty()
        pg.click('[data-acao="tele-verificar"]')
        expect(pg.locator("#tele-lista .tele-jogo")).to_have_count(6)
        r = pg.request.post(BASE + "/api/telemetria/ajustar", data=json.dumps({"jogo": "ams2"}),
                            headers={"Content-Type": "application/json", "Origin": BASE})
        assert r.json()["ok"] is False, "AMS2 não deveria ter ajuste automático"
    _()

    if not celular:
        @caso(G, "Ao vivo: janela separada sem barra lateral", pg)
        def _():
            abrir("#/aovivo")
            with pg.expect_popup() as info:
                pg.click('.so-painel [data-acao="vivo-janela"]')
            jan = info.value
            jan.wait_for_load_state()
            jan.locator("#vivo .cartao").wait_for()
            assert jan.evaluate("document.body.classList.contains('janela')"), "a janela não entrou no modo Ao vivo"
            assert not jan.locator(".side").is_visible(), "a barra lateral aparece na janela"
            jan.close()
        _()

        @caso(G, "Conteúdo centralizado em tela grande", pg)
        def _():
            pg.set_viewport_size({"width": 2560, "height": 1080})
            abrir("#/sessoes")
            caixa = pg.locator("#conteudo > .cartao").first.bounding_box()
            main = pg.locator("#conteudo").bounding_box()
            esq = caixa["x"] - main["x"]
            dir_ = (main["x"] + main["width"]) - (caixa["x"] + caixa["width"])
            assert abs(esq - dir_) < 40, f"conteúdo não está no centro (esq {esq:.0f}, dir {dir_:.0f})"
            pg.set_viewport_size({"width": 1400, "height": 900})
        _()

    @caso(G, "Indicador de status: abrir, relatar problema, fechar", pg)
    def _():
        abrir("#/")
        pg.click(".ind-btn")
        expect(pg.locator("#ind-painel")).to_be_visible()
        pg.fill("#rel-texto", "teste automático")
        pg.click('[data-acao="relatorio-enviar"]')
        expect(pg.locator("#rel-res")).to_contain_text(".zip")
        pg.keyboard.press("Escape")
        expect(pg.locator("#ind-painel")).to_be_hidden()
    _()

    @caso(G, "Ao vivo: sem jogo mostra 'aguardando'", pg)
    def _():
        abrir("#/aovivo")
        pg.locator("#vivo .cartao").wait_for()
        expect(pg.locator("#vivo")).to_contain_text("Aguardando")
    _()

    @caso(G, "Segurança: outro site não consegue mandar comandos", pg)
    def _():
        r = pg.request.post(BASE + "/api/pendencias/nova", data="texto=invasao", headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status == 403, f"aceitou formulário de fora ({r.status})"
        r = pg.request.post(BASE + "/api/pendencias/nova", data=json.dumps({"texto": "x"}),
                            headers={"Content-Type": "application/json", "Origin": "http://site-malicioso.com"})
        assert r.status == 403, f"aceitou outra origem ({r.status})"
    _()
    pg.close()


# ------------------------------------------------------------------ 3. macaco (gremlins.js)
def servir_gremlins(rota):
    nome = rota.request.url.split("/__gremlins/", 1)[1].split("?")[0]
    arq = os.path.normpath(os.path.join(GREMLINS, nome))
    if not arq.endswith(".js"):
        arq += ".js"
    if not arq.startswith(GREMLINS) or not os.path.exists(arq):
        return rota.fulfill(status=404, body="")
    with open(arq, encoding="utf-8") as f:
        corpo = f.read().replace("from 'chance'", "from '/__gremlins/chance.js'").replace('from "chance"', "from '/__gremlins/chance.js'")
    rota.fulfill(status=200, body=corpo, headers={"Content-Type": "text/javascript"})


def macaco(ctx):
    pg = ctx.new_page()
    pg.route("**/__gremlins/**", servir_gremlins)
    for nome, rota, _ in TELAS:
        @caso("Macaco (gremlins.js)", f"{nome}: 600 ações aleatórias", pg)
        def _():
            pg.goto(BASE + "/" + rota)
            pg.locator("main h1").first.wait_for()
            seletor = ",".join(f"[data-acao='{a}']" for a in PERIGOSOS) + ",a[href^='/api/']"
            pg.add_style_tag(content=seletor + "{pointer-events:none!important}")
            pg.evaluate("""() => { window.alert = () => {}; window.confirm = () => true; window.prompt = () => ''; }""")
            res = pg.evaluate("""async () => {
              const g = await import('/__gremlins/index.js');
              const erros = [];
              window.addEventListener('error', (e) => erros.push(String(e.message)));
              const h = g.createHorde({ randomizer: new g.Chance(2026), species: [g.species.clicker(), g.species.toucher(), g.species.formFiller(), g.species.scroller(), g.species.typer()],
                mogwais: [g.mogwais.gizmo({ maxErrors: 10 })], strategies: [g.strategies.distribution({ nb: 600, delay: 3 })] });
              await h.unleash();
              return erros;
            }""")
            assert not res, "; ".join(res[:3])
            # depois do macaco, o painel continua de pé
            pg.goto(BASE + "/#/")
            pg.locator("main h1").first.wait_for(timeout=10000)
        _()
    pg.close()


# ------------------------------------------------------------------ 4. varredura (estilo buttonmash)
def varredura(ctx):
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)[:200]))
    pg.on("response", lambda r: erros.append(f"HTTP {r.status} em {r.url}") if r.status >= 500 else None)
    pg.on("dialog", lambda d: d.dismiss())
    total = 0
    for nome, rota, _ in TELAS:
        pg.goto(BASE + "/" + rota)
        pg.locator("main h1").first.wait_for()
        alvos = pg.locator("main button, main a[href], main input[type=checkbox], main input[type=radio], main select, aside button, aside a").evaluate_all(
            """els => els.map((e, i) => ({i, acao: e.dataset.acao || '', href: e.getAttribute('href') || '', tag: e.tagName, txt: (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 40)}))""")
        clicados = 0
        for a in alvos:
            if a["acao"] in PERIGOSOS or a["href"].startswith("/api/"):
                continue
            pg.goto(BASE + "/" + rota)
            pg.locator("main h1").first.wait_for()
            el = pg.locator("main button, main a[href], main input[type=checkbox], main input[type=radio], main select, aside button, aside a").nth(a["i"])
            try:
                if not el.is_visible() or not el.is_enabled():
                    continue
                if a["tag"] == "SELECT":
                    n = el.locator("option").count()
                    if n > 1:
                        el.select_option(index=n - 1)
                else:
                    el.click(timeout=3000)
                clicados += 1
                pg.wait_for_timeout(120)
                corpo = pg.locator("main").inner_text(timeout=3000)
                if not corpo.strip() or "Não consegui carregar" in corpo:
                    erros.append(f"{nome}: tela em branco ou com erro depois de clicar em '{a['txt'] or a['acao'] or a['href']}'")
            except Exception as e:
                erros.append(f"{nome}: '{a['txt'] or a['acao'] or a['href']}' não respondeu ({type(e).__name__})")
        total += clicados
        registrar("Varredura de botões", f"{nome}: {clicados} controles clicados", not erros, "; ".join(erros[:4]))
        erros.clear()
    pg.close()
    return total


# ------------------------------------------------------------------ relatório
def relatorio(inicio):
    ok = sum(1 for r in resultados if r[2])
    grupos = []
    for g in dict.fromkeys(r[0] for r in resultados):
        linhas = "".join(
            f"<tr class='{'ok' if r[2] else 'falha'}'><td>{'✔' if r[2] else '✘'}</td><td>{html.escape(r[1])}</td><td>{html.escape(r[3])}</td>"
            f"<td>{f'<a href=\"{r[4]}\" target=\"_blank\"><img src=\"{r[4]}\" loading=\"lazy\"></a>' if r[4] else ''}</td></tr>"
            for r in resultados if r[0] == g)
        grupos.append(f"<h2>{html.escape(g)}</h2><table>{linhas}</table>")
    telas = sorted(f for f in os.listdir(os.path.join(REL, "telas")) if f.startswith("tela-"))
    galeria = "".join(f"<figure><a href='telas/{f}' target='_blank'><img src='telas/{f}'></a><figcaption>{f[5:-4]}</figcaption></figure>" for f in telas)
    pagina = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Validação do Axtel</title>
<style>body{{font:15px system-ui;background:#0D1015;color:#E7EAEE;margin:0;padding:24px;max-width:1200px}}h1{{margin:0}}
.res{{font-size:20px;margin:8px 0 20px}}table{{width:100%;border-collapse:collapse;margin-bottom:20px}}td{{padding:6px 8px;border-bottom:1px solid #252C36;vertical-align:top}}
tr.ok td:first-child{{color:#2FD27A}}tr.falha td{{background:#2a1416}}tr.falha td:first-child{{color:#FF5555}}td img{{width:160px;border:1px solid #252C36;border-radius:4px}}
td:nth-child(3){{color:#8C95A2;font-size:13px}}figure{{display:inline-block;margin:0 12px 12px 0;width:260px}}figure img{{width:100%;border:1px solid #252C36}}figcaption{{color:#8C95A2;font-size:13px}}</style>
<h1>Validação do Axtel 1.5</h1><div class="res">{ok} de {len(resultados)} verificações passaram · {time.strftime('%d/%m/%Y %H:%M')} · {int(time.time() - inicio)} s</div>
{''.join(grupos)}<h2>Todas as telas</h2>{galeria}</html>"""
    with open(os.path.join(REL, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina)
    return ok


def main():
    inicio = time.time()
    shutil.rmtree(REL, ignore_errors=True)
    os.makedirs(os.path.join(REL, "telas"))
    proc = simulacao()
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pc = nav.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
            roteiro(pc)
            cel = nav.new_context(**p.devices["Pixel 7"])
            roteiro(cel, celular=True)
            macaco(pc)
            varredura(pc)

            @caso("Roteiro PC", "Fechar o Axtel pelo painel (último teste)")
            def _():
                pg = pc.new_page()
                pg.goto(BASE + "/#/config")
                pg.locator("main h1").first.wait_for()
                pg.click('[data-acao="fechar-app"]')
                pg.click('[data-acao="fechar-nao"]')
                pg.click('[data-acao="fechar-app"]')
                pg.click('[data-acao="fechar-sim"]')
                expect(pg.locator("body")).to_contain_text("Axtel fechado")
                pg.wait_for_timeout(2000)
                try:
                    api("/api/status")
                    raise AssertionError("o Axtel continuou rodando")
                except AssertionError:
                    raise
                except Exception:
                    pass
            _()
            nav.close()
    except Exception:
        traceback.print_exc()
        registrar("Geral", "o validador terminou sem erro", False, traceback.format_exc().splitlines()[-1])
    finally:
        proc.terminate()
    ok = relatorio(inicio)
    print(f"\n{ok} de {len(resultados)} verificações passaram. Relatório: {os.path.join(REL, 'index.html')}")
    sys.exit(0 if ok == len(resultados) else 1)


if __name__ == "__main__":
    main()
