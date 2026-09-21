# Residencial Aurora — assistente virtual

Assistente do Residencial Aurora construído com o Google ADK e exposto por uma
API FastAPI, seguindo o contrato do desafio (`Challenge.md`). O morador
conversa com um agente principal, que distribui o trabalho entre
especialistas; reservas, visitantes e regulamento são sempre lidos e gravados
por tools em código, nunca por algo que o modelo lembra ou inventa.

## Arquitetura

```
app/
  main.py              rotas da API (FastAPI)
  runner_service.py     liga a API ao Runner do ADK (sessão, turnos, confirmações)
  agents/
    root_agent.py        monta o agente principal e os 3 especialistas
    apartamento.py        único ponto de leitura do apartamento da sessão
    tools_reservas.py     tools do especialista em reservas
    tools_visitantes.py   tools do especialista em visitantes
    tools_regulamento.py  tool do especialista em regulamento
  storage/
    db.py                 SQLite de reservas/visitantes (gravação e restauração)
    catalogo.py            leitura de dados/apartamentos.json e dados/areas.json
    regulamento.py          divisão do regulamento em capítulos
```

### Agente principal e especialistas

O **agente principal** (`agente_principal`, em `app/agents/root_agent.py`) é
o único ponto de contato do morador. Ele não tem nenhuma tool própria: sua
única função é entender o pedido e transferir a conversa para um dos três
especialistas, usando a transferência nativa do ADK (`sub_agents`, não uma
tool `AgentTool`). Essa escolha não é só estilística — ver a nota técnica no
final desta seção.

- **`especialista_reservas`** (`app/agents/tools_reservas.py`): listar áreas
  comuns, verificar disponibilidade, listar as reservas do morador, criar e
  cancelar reservas do salão de festas, churrasqueira e quadra.
- **`especialista_visitantes`** (`app/agents/tools_visitantes.py`): listar e
  autorizar visitantes.
- **`especialista_regulamento`** (`app/agents/tools_regulamento.py`):
  responde dúvidas sobre o regulamento interno, buscando o capítulo certo em
  `dados/regulamento.md` a cada pergunta (nunca lendo o documento inteiro).

Três especialistas foram suficientes para separar claramente as três
"famílias" de regra de negócio do desafio (reserva, visitante, regulamento),
cada uma com sua própria fonte de dados e sua própria política de
confirmação — dividir mais que isso não agregaria clareza para o escopo
atual.

**Nota técnica — por que `sub_agents` e não `AgentTool`:** a Garantia 1
depende de o ADK conseguir retomar, depois de `POST
/sessoes/{id}/confirmacoes`, exatamente o agente que pediu a confirmação.
Isso é decidido por `find_agent_to_run` (ADK, `agents/_agent_router.py`),
que procura, na árvore de agentes do `Runner`, quem é o autor do evento de
confirmação pendente. Um especialista chamado via `AgentTool` roda numa
execução aninhada cujo autor não aparece dessa forma na árvore principal, o
que quebra essa retomada. Com transferência real (`sub_agents`), o
especialista aparece como autor de primeira classe na sessão, e a retomada
funciona — isso foi validado na prática (não só lido no código), incluindo
com a sessão persistida em SQLite e depois de reiniciar a API.

## Garantias

Cada garantia abaixo é decidida por código que não depende de nada que o
modelo "decida" dizer — o texto ao lado de cada trecho explica por quê.

### Garantia 1 — cobrança ou acesso só com confirmação

- `app/agents/tools_reservas.py:103` — `FunctionTool(criar_reserva,
  require_confirmation=_area_tem_taxa)`: a tool só executa `criar_reserva`
  depois de aprovação quando a área tem taxa. `_area_tem_taxa`
  (`tools_reservas.py:46`) olha o catálogo de áreas (`dados/areas.json`), não
  o texto do morador.
- `app/agents/tools_visitantes.py:39` — `FunctionTool(autorizar_visitante,
  require_confirmation=True)`: autorizar visitante **sempre** pede
  confirmação, mesmo que a mensagem diga "já confirmei" — esse texto nunca
  chega perto da decisão, porque quem decide é o parâmetro
  `require_confirmation`, resolvido pelo próprio `FunctionTool` do ADK antes
  de chamar a função Python.
- `app/runner_service.py:154` (`_confirmacoes_pendentes`) — a lista de
  confirmações pendentes é calculada lendo os eventos reais da sessão
  (chamadas de função sintéticas `adk_request_confirmation` sem uma
  `function_response` correspondente), nunca a partir do que o modelo
  escreveu em texto.
- `app/runner_service.py:92-99` (`responder_confirmacao`) — a rota de
  confirmações só aceta um `id` que está nessa lista; qualquer outro (de uma
  confirmação já respondida ou inexistente) levanta `ConfirmacaoNaoPendente`,
  traduzido em `app/main.py` para `409`, e o `Runner` nem chega a ser
  chamado.

### Garantia 2 — cada sessão pertence a um apartamento

- `app/runner_service.py:64-69` (`criar_sessao`) — o apartamento é gravado
  uma única vez, no `state` da sessão do ADK, no momento de `POST /sessoes`.
- `app/agents/apartamento.py:20` (`apartamento_da_sessao`) — toda tool que
  precisa saber "de quem é essa conversa" chama esta função, que só lê
  `tool_context.state["apartamento"]`. Nenhuma tool de
  `tools_reservas.py`/`tools_visitantes.py` tem um parâmetro "apartamento"
  que o modelo possa preencher; o valor nunca vem de um argumento de função
  escolhido pelo modelo, só do state da sessão.
- `app/agents/tools_reservas.py` (`verificar_disponibilidade`) — ao checar
  agenda, a tool devolve só `{"livre": bool}`; o apartamento dono de uma
  reserva nunca é lido do banco para essa checagem, então não tem como
  vazar para a conversa.

### Garantia 3 — nada se perde no reinício

- `app/runner_service.py:60` — `DatabaseSessionService(db_url=SESSIONS_DB_URL)`
  usa SQLite (`.data/sessoes.db`) para persistir sessões e eventos; não há
  serviço de sessão em memória em nenhum caminho de código.
- `app/storage/db.py` — reservas e visitantes vivem em `.data/condominio.db`,
  outro arquivo SQLite, gravado a cada `criar_reserva`/`cancelar_reserva`/
  `autorizar_visitante`.
- Validado na prática: depois de derrubar e subir a API de novo,
  `GET /sessoes/{id}/eventos` devolve exatamente os mesmos eventos de antes,
  uma nova mensagem na mesma sessão funciona normalmente, e todas as
  reservas/visitantes gravados antes do reinício continuam valendo.

### Garantia 4 — o regulamento é consultado, não carregado

- `app/agents/root_agent.py` — a instrução do `agente_principal`
  (`_INSTRUCAO_PRINCIPAL`) nunca contém o texto do regulamento; ele só sabe
  que existe um `especialista_regulamento` para esse assunto.
- `app/storage/regulamento.py` (`listar_capitulos`, `buscar_capitulo`) — o
  regulamento é dividido em capítulos uma vez, em memória; `buscar_capitulo`
  escolhe o capítulo mais relevante por sobreposição de palavras-chave.
- `app/agents/tools_regulamento.py` (`consultar_regulamento`) — a tool
  devolve o texto de **um único capítulo**. É esse texto — e só ele — que
  vira o resultado de tool nos eventos da sessão; nenhum outro capítulo
  aparece. Validado na prática: a pergunta "até que horas a piscina funciona
  aos domingos" gera um evento de tool cujo `texto` contém somente o
  Capítulo IV (Piscina), sem nenhum trecho de outro capítulo.

### Garantia 5 — dois moradores, uma reserva

- `app/storage/db.py:32` — `CREATE UNIQUE INDEX ... idx_reservas_area_data_ativa
  ON reservas(area, data) WHERE status = 'ativa'`: a exclusividade é uma
  restrição do próprio SQLite, verificada pelo banco no instante do
  `INSERT`, não por uma consulta feita em Python antes de gravar.
- `app/storage/db.py:123` (`criar_reserva`) — tenta o `INSERT`; se o SQLite
  recusar por violar esse índice (`sqlite3.IntegrityError` mencionando
  `reservas.area, reservas.data`), a função devolve `None` e a tool
  correspondente responde normalmente (`{"reservada": False, "motivo":
  "..."}`), sem exceção não tratada e sem `500`.
- Duas inserções concorrentes para a mesma área/data são serializadas pelo
  próprio arquivo do banco (SQLite com `PRAGMA busy_timeout`); a que perde
  recebe o erro de violação de índice exatamente no commit, nunca antes.
  Validado com um teste de concorrência real (duas threads chamando
  `criar_reserva` ao mesmo tempo) e, de ponta a ponta, com duas sessões
  aprovando a mesma reserva simultaneamente pela API: as duas respostas
  voltam `200`, e só uma reserva existe no final.

## Como rodar

### Pré-requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Uma chave do [Google AI Studio](https://aistudio.google.com/apikey)

### Configuração

```bash
cp .env.example .env
# edite .env e preencha GOOGLE_API_KEY
```

Variáveis do `.env`:

| Variável | Descrição |
|---|---|
| `GOOGLE_API_KEY` | Chave do Google AI Studio usada pelos agentes. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Mantenha `FALSE` para usar o Google AI Studio. |
| `ADK_MODEL` | Modelo Gemini usado por todos os agentes (principal e especialistas). |

### Instalar

```bash
uv sync
```

### Restaurar os dados

Recarrega reservas e visitantes a partir de `dados/reservas.json` e
`dados/visitantes.json`, apagando qualquer alteração feita pelo assistente.
Não apaga sessões de conversa.

```bash
uv run python -m app.restore
```

### Subir a API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

A API sobe em `http://localhost:8000`. Na primeira execução (ou depois de
restaurar), `GET /apartamentos/101/reservas` deve listar a `RSV-1377` e
`GET /apartamentos/302/visitantes` deve listar Marina Duarte.

Armazenamento: SQLite em arquivos locais dentro de `.data/` (criados
automaticamente, fora do controle de versão) — não depende de nenhum serviço
externo.
