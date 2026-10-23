# SecOn Dbrain

SecOn Dbrain mantém um índice local de PDFs e arquivos Markdown para você pesquisar sua coleção. O RAG (geração aumentada por recuperação) encontra trechos relevantes durante a pergunta e pode fornecê-los como contexto a uma IA; isso não treina nem ajusta o modelo. A CLI permite usar a coleção sem IA.

## Onde guardar cada conteúdo

Os READMEs de cada pasta explicam como usá-la. PDFs e arquivos pessoais são adicionados apenas à sua cópia local.

| Pasta | O que guardar | Busca |
|---|---|---|
| [00-Inicio](00-Inicio/README.md) | Orientações e mapas próprios em Markdown | Sim |
| [10-Fontes](10-Fontes/README.md) | Fichas bibliográficas e estudos de caso em Markdown | Sim |
| [20-Notas](20-Notas/README.md) | Conceitos e anotações próprias em Markdown | Sim |
| [30-Procedimentos](30-Procedimentos/README.md) | Procedimentos, checklists e ferramentas em Markdown | Sim |
| [40-Experimentos](40-Experimentos/README.md) | Experimentos e writeups em Markdown | Sim |
| [Livros](Livros/README.md) | Livros em PDF | Sim |
| [Documentos](Documentos/README.md) | Manuais, documentações e relatórios em PDF | Sim |
| [Markdown](Markdown/README.md) | Documentação de referência original em `.md` | Sim |
| [Anexos](Anexos/README.md) | Imagens e evidências | Não |
| [90-Templates](90-Templates/README.md) | Oito templates opcionais para novas notas | Não |
| [Sistema](Sistema/README.md) | Código e configuração | Não |

Fichas bibliográficas de livros ficam em [10-Fontes/Livros/](10-Fontes/Livros/README.md). Os READMEs de orientação têm `rag_exclude: true`; anexos, templates e Sistema não são indexados.

## Início rápido

O projeto requer Python 3.12 e Git. Ele separa a indexação da consulta: durante a indexação, extrai texto, registra metadados e localizadores, divide o conteúdo em trechos de até 400 tokens com sobreposição de até 40 tokens e calcula embeddings em CPU via ONNX. Durante a consulta, combina BM25 com SQLite FTS5 e busca vetorial por cosseno em NumPy; a fusão RRF ordena candidatos. O MCP só lê o índice e não atualiza documentos.

### Windows

Instale Git e Python 3.12, com Python disponível no PATH. No PowerShell, clone e prepare o ambiente:

```powershell
python --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
Set-Location secon-dbrain-mcp
python Sistema/setup_environment.py
.venv\Scripts\python.exe Sistema/dbrain.py setup-model
```

Agora copie seus PDFs para `Livros/` ou `Documentos/` e seus Markdown para as pastas da tabela acima. Depois de adicionar arquivos, indexe e pesquise:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py update
.venv\Scripts\python.exe Sistema/dbrain.py status
.venv\Scripts\python.exe Sistema/dbrain.py search 'sua pergunta ou tema'
```

### Ubuntu 24.04 x86_64

No terminal, instale Git, Python 3.12 e o suporte a ambientes virtuais, depois clone e prepare o ambiente:

```bash
sudo apt update
sudo apt install git python3.12 python3.12-venv
python3.12 --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
cd secon-dbrain-mcp
python3.12 Sistema/setup_environment.py
.venv/bin/python Sistema/dbrain.py setup-model
```

Agora copie seus PDFs para `Livros/` ou `Documentos/` e seus Markdown para as pastas da tabela acima. Depois de adicionar arquivos, indexe e pesquise:

```bash
.venv/bin/python Sistema/dbrain.py update
.venv/bin/python Sistema/dbrain.py status
.venv/bin/python Sistema/dbrain.py search 'sua pergunta ou tema'
```

`setup-model` baixa o modelo de embeddings fixado pelo projeto e precisa de rede. Após o download, indexação e busca rodam localmente em CPU. O wrapper `dbrain.ps1` é opcional no Windows. O guia [Uso](docs/usage.md) contém exemplos de criação de notas e a configuração completa do MCP.

## MCP e cliente de IA

O MCP local oferece `search_knowledge`, `read_knowledge` e `knowledge_status`, ferramentas somente de leitura. Usa transporte STDIO e não inicia servidor HTTP. Para gerar uma configuração genérica, execute:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target generic
```

No Ubuntu, use `.venv/bin/python Sistema/install_agents.py --target generic`. O instalador apenas imprime um JSON de exemplo; ele não altera o cliente. Copie o objeto `mcpServers` apenas em clientes que aceitam esse formato. Nos outros, cadastre os mesmos valores de `command`, `args` e `env` na estrutura própria do cliente. Reinicie a sessão para carregar o servidor e peça à IA para pesquisar, ler os trechos e citar a página física do PDF ou a seção/linhas do Markdown. Integrações opcionais com Codex e Claude podem ser aplicadas pelo instalador com `--target codex --apply` ou `--target claude --apply`.

## Evidência e privacidade

Resultados são candidatos de busca, não respostas verificadas. Confira afirmações importantes na fonte original. Extração de PDFs pode perder estrutura; OCR com Tesseract é opcional, seletivo e requer revisão. Trechos enviados pelo MCP podem chegar ao provedor de IA escolhido para a conversa. Não indexe segredos nem material que não possa ser enviado a esse serviço.

Obsidian é opcional; qualquer editor compatível com Markdown serve. Consulte [licença](LICENSE), [contribuições](CONTRIBUTING.md) e [segurança](SECURITY.md).
