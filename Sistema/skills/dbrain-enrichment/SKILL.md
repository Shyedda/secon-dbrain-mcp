---
name: dbrain-enrichment
description: Planejar tarefas pequenas de enriquecimento SecOn Dbrain e produzir resumos derivados com citações precisas às evidências retornadas.
---

# Enriquecimento SecOn Dbrain

A biblioteca fica em `{{root}}`; use MCP `{{mcp_name}}`. Antes de escolher fontes, leia `input_dirs` em `Sistema/config.json`. Planejamento usa apenas fontes nas entradas configuradas; elas podem incluir uma pasta privada existente como `Livros/`. Não mova nem renomeie originais para adotar os caminhos padrão da distribuição.

Use somente quando o usuário pedir para sintetizar ou enriquecer conhecimento a partir da biblioteca. Enriquecimento é opcional e progressivo; não tente resumir toda a coleção por padrão. Antes de gravar, confirme que o servidor MCP foi iniciado com `--allow-writes` ou use a CLI local de envio.

## Planejar um lote

Escolha a pergunta, fonte ou tema que atende à necessidade atual. Os limites são 1 a 10 tarefas e 1000 a 12000 tokens estimados de entrada por tarefa. Comece com os padrões modestos de três tarefas e 4000 tokens; o orçamento é uma estimativa, não uma garantia de cobrança ou cobertura.

MCP:

```text
plan_enrichment(query?, source_ids?, max_tasks=3, max_input_tokens=4000)
```

CLI:

```text
dbrain.py enrichment-plan [--query TEMA] [--source-id ID] [--max-tasks 3] [--max-input-tokens 4000]
```

Use os IDs de fonte retornados. Cada tarefa representa apenas um segmento parcial de uma unidade, não um capítulo inteiro. Se o plano não encontrar evidência suficiente ou o orçamento excluir conteúdo relevante, refine o tema ou planeje outro lote; não declare cobertura completa.

## Ler e redigir

Leia cada tarefa antes de escrever:

```text
read_enrichment_task(task_id)
dbrain.py enrichment-read TASK_ID
```

Leia a referência retornada. Cada tarefa fornece uma lista `references` com uma única citação identificada como `0`. Redija apenas sobre o segmento recebido, diferencie afirmações da fonte de inferências e explicite que a cobertura é parcial. Coloque literalmente `[0]` no corpo onde a evidência sustenta a afirmação, preservando página física, seção ou linhas retornadas. Não invente fatos, relações semânticas, fontes, páginas, citações, resultados ou experimentos executados. Se o trecho não sustenta o resumo, não o envie como conclusão.

## Enviar e revisar

MCP:

```text
submit_enrichment(task_id, title, summary, citations: list[int], by='agent')
```

CLI:

```text
dbrain.py enrichment-submit TASK_ID --file resumo.json --by agent
```

O arquivo JSON deve conter `title`, `summary` e `citations`; o contrato exige `citations: [0]` e o literal `[0]` em `summary`. `title` deve ter 1 a 200 caracteres em uma linha; `summary`, 20 a 16000 caracteres. O envio cria um derivado em `knowledge_dir` (padrão `Conhecimento/20-Notas/`), indexa-o e registra `source_refs`, incluindo hash e localizador da fonte. O resumo começa com `status: needs-review`. A validação confere formato/citação e a versão da fonte, mas não comprova fidelidade semântica; não o marque como revisado sem revisão autorizada. Se a fonte mudar ou desaparecer, o resumo derivado obsoleto é excluído da recuperação; planeje uma nova tarefa após atualizar as fontes. Não sobrescreva uma nota humana. Se já existir nota equivalente, complemente-a apenas quando a operação permitir edição segura e o usuário tiver solicitado essa mudança.

Os escritores MCP `plan_enrichment` e `submit_enrichment` só ficam disponíveis com `--allow-writes`; a leitura `read_enrichment_task` está sempre disponível. Os trechos da tarefa podem ser enviados ao provedor de IA usado na conversa. O fluxo não treina o modelo e não exige nova API de geração do projeto. Verifique o resumo contra as fontes originais antes de usá-lo como informação estabelecida. Para os detalhes operacionais, consulte `{{root}}/docs/usage.md`; se esse arquivo não existir na biblioteca privada, consulte `{{root}}/Sistema/README.md`.
