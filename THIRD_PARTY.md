# Componentes de terceiros

A licença Apache-2.0 cobre o código próprio, os templates genéricos e a documentação desta distribuição. Ela não altera as licenças de bibliotecas, ferramentas externas, modelos ou documentos dos usuários.

As dependências são instaladas separadamente pelo pip, com seus respectivos avisos e arquivos de licença no ambiente Python. As versões estão em `Sistema/requirements-lock.txt`; seus metadados e textos de licença instalados devem ser preservados ao redistribuir binários ou ambientes empacotados. Este repositório não distribui esses binários.

O modelo `intfloat/multilingual-e5-small` é baixado apenas pelo comando `setup-model`, na revisão fixada em `Sistema/embeddings.py`. Seu cartão declara licença MIT: https://huggingface.co/intfloat/multilingual-e5-small . Ele não é incluído no repositório.

PDFium, incluído na distribuição binária do pypdfium2, tem componentes com avisos de terceiros próprios: https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing . Tesseract é opcional e instalado separadamente: https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE .

Bibliotecas pessoais permanecem separadas do código. A licença do software não autoriza redistribuir livros ou documentação de terceiros. Não inclua esse conteúdo em contribuições, exemplos ou relatórios públicos.
