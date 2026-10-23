---
name: dbrain-setup
description: Instalar ou preparar uma coleção SecOn Dbrain a partir de fontes PDF e Markdown, configurar o índice local e conectar opcionalmente o MCP.
---

# Configurar SecOn Dbrain

Use para instalação inicial, configuração ou preparação de uma biblioteca. A biblioteca fica em `{{root}}`; use MCP `{{mcp_name}}`. Consulte `{{root}}/docs/usage.md` para comandos de Windows e Ubuntu 24.04; se não existir, consulte `{{root}}/Sistema/README.md`.

## Estrutura esperada

- Fontes originais: os diretórios PDF e Markdown configurados em `Sistema/config.json` em `input_dirs` (a distribuição usa `PDFs/` e `Markdown/` por padrão; uma biblioteca privada existente pode manter PDF em `Livros/`).
- Conhecimento derivado: o diretório configurado em `knowledge_dir` (padrão `Conhecimento/`), com subpastas `00-Inicio`, `10-Fontes`, `20-Notas`, `30-Procedimentos`, `40-Experimentos` e `90-Templates`.
- Índice, extrações, trechos, embeddings, mapas e cache: `.dbrain/`.
- Templates e guias README não são indexados.

Leia `input_dirs` antes de preparar a coleção. Trate somente arquivos das entradas configuradas como fontes; não assuma os caminhos padrão nem mova fontes existentes. Preserve bytes, nomes e localização dos originais. Não reimporte por cima de notas humanas.

## Preparar

Use Python 3.12 e o ambiente local do projeto. Baixe o modelo fixado somente quando o modo híbrido precisar dele. Para preparação inicial, prefira a CLI num terminal próprio, pois pode demorar:

```text
dbrain.py prepare [--path CAMINHO] [--lexical] [--wait 900] [--by agent]
```

Use `--path` para atualizar fontes específicas ou diretórios alterados e `--wait 900` para aguardar a trava de escrita. `--lexical` seleciona um índice sem embeddings. Preserve a modalidade já escolhida na coleção, a menos que o usuário solicite uma mudança. Nunca apague `writer.lock`.

`prepare` atualiza a camada Silver: extração, trechos, embeddings quando aplicável, recuperação lexical/vetorial, fusão RRF e mapas heurísticos locais por termos. Os mapas não afirmam relações semânticas verificadas. Esses produtos ajudam na busca, mas podem estar incompletos ou errados. A CLI é o caminho recomendado para primeira preparação; `prepare_knowledge(paths?)` via MCP é integração opcional para atualizações locais incrementais.

## MCP opcional

Configure o cliente com `Sistema/install_agents.py --target generic`. Para imprimir uma configuração MCP com os escritores habilitados, acrescente `--allow-writes` somente quando esse modo for solicitado. Sem a opção, a integração permanece somente de leitura. MCP usa trechos no contexto da conversa e o provedor de IA pode recebê-los.

Não execute enriquecimento completo da coleção como parte da configuração. Para resumos por tarefas, use a skill `dbrain-enrichment` quando essa necessidade for solicitada. Não prometa conhecimento completo, precisão garantida ou treinamento do modelo.
