# SecOn Dbrain

SecOn Dbrain é uma ferramenta local para pesquisar uma coleção pessoal de PDFs e arquivos Markdown. Ela extrai texto, divide o conteúdo em trechos com localizadores e cria um índice lexical e vetorial no próprio computador. Um servidor MCP opcional permite que um assistente consulte esse índice.

O índice é uma forma de recuperação de informação (RAG): no momento de uma pergunta, a busca encontra trechos relevantes para fornecer contexto ao modelo. Isso não treina, ajusta nem altera o modelo. O assistente pode receber os trechos recuperados e processá-los conforme o serviço e a configuração usados na conversa; o conteúdo não é enviado durante a indexação ou por uma busca local sem MCP.

## Requisitos e instalação

Python 3.12 é necessário. A configuração cria um ambiente virtual próprio em `.venv`, independente dos pacotes Python do sistema. A suíte automatizada cobre Windows e Ubuntu 24.04 x86_64. Uma validação real em Ubuntu 24.04.2 no WSL2, com Python 3.12.15, verificou PDF, Markdown, embeddings em CPU, MCP STDIO, atualização incremental, lock entre processos e OCR em português/inglês. ARM64 e macOS ainda não foram validados.

Clone o repositório público e entre na pasta:

```powershell
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
Set-Location secon-dbrain-mcp
```

Na raiz clonada, execute:

```powershell
python Sistema/setup_environment.py
```

Se o Python 3.12 não estiver no `PATH`, informe seu executável:

```powershell
python Sistema/setup_environment.py --python 'C:\caminho\para\python.exe'
```

O comando instala as dependências no ambiente do projeto. Baixe explicitamente o modelo de embeddings fixado pelo projeto:

```powershell
.\dbrain.ps1 setup-model
```

No Windows, `dbrain.ps1` é o atalho para a CLI. Em Unix, use `.venv/bin/python Sistema/dbrain.py`; por exemplo, `.venv/bin/python Sistema/dbrain.py setup-model`.

## Preparar uma coleção

Coloque PDFs em `Documentos/` e Markdown em `Notas/`. As pastas são locais à sua cópia do projeto. Os arquivos em `90-Templates/` são modelos opcionais para suas próprias notas, e Obsidian é uma opção de editor, não um requisito. A configuração de indexação fica em `Sistema/config.json`; dados derivados, como índice, extrações e modelo baixado, ficam em `.dbrain/` e não devem ser tratados como documentos de origem.

Depois de adicionar arquivos, atualize o índice:

```powershell
.\dbrain.ps1 update
```

Para indexar apenas um caminho, use `update --path` com um arquivo ou pasta sob a raiz. Para uma coleção que ainda não tem índice híbrido, uma alternativa explicitamente lexical é:

```powershell
.\dbrain.ps1 update --lexical
```

Esse modo não usa embeddings. Não use `--lexical` para substituir o índice híbrido de uma coleção existente. Em Unix, os mesmos subcomandos podem ser executados com `.venv/bin/python Sistema/dbrain.py`.

## Consultar

Uma busca local pode ser feita pela CLI:

```powershell
.\dbrain.ps1 search 'tema ou pergunta'
.\dbrain.ps1 read 'source-id' --page 12
.\dbrain.ps1 status
```

O MCP oferece três ferramentas de consulta:

- `search_knowledge` encontra trechos candidatos e retorna identificadores e localizadores.
- `read_knowledge` abre um trecho de uma fonte indexada, usando o localizador da busca.
- `knowledge_status` informa estado e cobertura detectável do índice; não indexa novos arquivos.

O MCP não expõe comandos de escrita. Para atualizações, use a CLI. O instalador gera a configuração MCP para integração genérica; a integração com Codex ou Claude é opcional e só altera a configuração do agente quando solicitada com `--apply`:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target generic
.venv\Scripts\python.exe Sistema/install_agents.py --target codex --apply
```

Confira `docs/usage.md` para instruções completas.

## Rastreabilidade e limites

Os resultados são candidatos de busca, não respostas verificadas. Para PDFs, confira o trecho na página física indicada; para Markdown, confira a seção e as linhas. A extração pode perder estrutura visual, tabelas, imagens ou texto em páginas digitalizadas. OCR seletivo com Tesseract é opcional e seus resultados precisam de conferência. A ferramenta não processa EPUB, DOCX ou HTML, não faz scraping genérico e não oferece serviço HTTP.

Uma boa prática é pedir ao assistente para ler os trechos citados, comparar a evidência com a pergunta e explicitar quando a coleção não sustenta uma conclusão. Fontes podem estar incompletas ou desatualizadas. Não coloque material que você não pode compartilhar no contexto de um provedor de IA: trechos retornados pelo MCP podem ser enviados ao serviço usado pela conversa.

## Configuração de domínio

O perfil geral usa a área `geral` por padrão. Um esquema opcional de segurança está em `Sistema/profiles/security/schema.json`; para ativá-lo, configure `schema_file` em `Sistema/config.json` para esse caminho. Ele acrescenta vocabulário de segurança sem tornar a ferramenta dependente desse domínio.

Uma skill genérica (`Sistema/skill/secon-dbrain/SKILL.md`) e oito templates Markdown também são opcionais e independentes do MCP. A skill orienta o agente a pesquisar, ler e citar resultados; os templates ajudam a criar notas. Ao instalar a integração com Codex ou Claude pelo instalador, a skill é instalada automaticamente junto com a integração. A coleção continua utilizável sem skill, templates, Obsidian ou MCP.

## Coleção em outra pasta

Use sempre o Python do ambiente `.venv` do repositório para a CLI quando apontar `--root` para uma coleção externa. A raiz externa precisa conter `Sistema/config.json`, `Sistema/schema.json` e os templates em `90-Templates/`, além das pastas de documentos configuradas; apontar apenas para uma pasta de PDFs não configura uma coleção válida.

## Licença e contribuições

Consulte o arquivo de licença na raiz do repositório. Orientações para contribuições e reporte de falhas estão em [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).
