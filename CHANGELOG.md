# Histórico de versões

## 1.5 — primeira versão pública
- Instalador: **Instalar Axtel** copia para a pasta do usuário, cria atalhos (Área de Trabalho e Menu Iniciar), registra em Configurações › Aplicativos e tem desinstalador que pergunta se guarda o histórico.
- `Axtel.exe` instala o Python 3.12 sozinho quando falta (winget ou instalador oficial do python.org, sem administrador) e ignora o atalho falso do Python da Microsoft Store.
- Repositório organizado para o GitHub, com testes automáticos e Release automática por tag.

## 1.4
- Ao vivo novo: carro e sessão (posição, volta, tempo restante, diferença à frente e atrás, bandeira), volante girando com o ângulo, três pedais, luzes de RPM, temperaturas do motor, pneus, combustível até o fim, condições e mapa com os outros carros.
- AC/ACC: um repique do tempo logo depois da linha marcava a volta seguinte como "volta de saída". Corrigido.
- Botão "Liberar som" libera o áudio de verdade (e qualquer clique no painel também).

## 1.3
- AMS2: estrutura da memória corrigida (12 parciais, não 15), que deslocava velocidade, RPM, marcha e combustível.
- Detecção dos jogos: prefere o jogo que está na pista com dados mudando; uma memória antiga (por exemplo mantida pelo SimHub) não prende mais o Axtel.
- Aviso quando o jogo roda como administrador e o Windows bloqueia a leitura.
- Configurações › Telemetria dos jogos, com ajuste automático para iRacing e F1 25.
- Ao vivo em janela separada e conteúdo centralizado em telas grandes.

## 1.2
- iRacing, Automobilista 2, F1 25 e Forza, além dos Assetto Corsa.
- Voz do ElevenLabs no spotter, setups, desafios e plano de treino, calendário com dias de melhora, comparação de várias voltas, backups automáticos, atalhos de teclado.
