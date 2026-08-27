# Biblioteca HCI

Sistema local para controlar os livros do endomarketing que ficam disponíveis para empréstimo no escritório.
Foi pensado para ser operado por uma pessoa responsável, sem contas de usuário e sem cadastro prévio dos assessores.

## O que controla

- Cadastro de livros da biblioteca.
- Registro de empréstimos informando apenas o nome completo do assessor.
- Registro de devoluções.
- Contagem automática de dias com o livro.
- Painel com livros disponíveis, emprestados e maior empréstimo em aberto.
- Histórico exportável em CSV.
- Backup local do banco de dados.

Não existe prazo fixo de devolução. A contagem de dias serve apenas para acompanhar há quanto tempo cada livro está fora do acervo.

## Como executar

1. Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

2. Inicie o sistema:

```powershell
python -m streamlit run app.py
```

3. Acesse o endereço exibido no terminal, normalmente:

```text
http://localhost:8501
```

## Como usar

1. Cadastre os livros em `Acervo`.
2. Quando alguém retirar um livro, registre em `Registrar empréstimo` e informe o nome completo do assessor.
3. Quando o livro voltar, registre em `Registrar devolução`.
4. Use `Visão geral` para ver com quem está cada livro e há quantos dias.
5. Use `Histórico` para consultar, filtrar ou baixar as movimentações.

O nome informado no primeiro empréstimo é reaproveitado automaticamente nas próximas movimentações. Não é necessário criar uma conta ou preencher um cadastro separado.

## Modelo de operação local

- Uma pessoa fica como ponto focal da Biblioteca HCI.
- O sistema pode ser aberto apenas quando houver uma retirada, uma devolução ou uma consulta.
- O computador não precisa permanecer ligado durante todo o dia.
- Fechar o navegador ou desligar o computador não apaga os registros.
- O arquivo do banco deve continuar no computador principal; mantenha cópias de backup em uma pasta segura da empresa.

## Publicar para mais de uma pessoa responsável

Quando duas pessoas precisarem registrar movimentações por um link, a configuração recomendada é:

- **Interface:** Streamlit Community Cloud.
- **Banco persistente:** Turso, compatível com o modelo SQLite atual.
- **Acesso:** uma senha compartilhada entre as pessoas responsáveis.

O aplicativo continua usando SQLite normalmente quando executado no computador. No ambiente publicado, ele ativa automaticamente o Turso quando encontra `TURSO_DATABASE_URL` e `TURSO_AUTH_TOKEN` nos Secrets do Streamlit.

### Configuração

1. Crie um banco no Turso importando `data/biblioteca.db`, para preservar os registros existentes.
2. Obtenha a URL e um token de acesso do banco.
3. Em [share.streamlit.io](https://share.streamlit.io), crie um aplicativo usando este repositório, a branch `main` e o arquivo `app.py`.
4. Em **Advanced settings > Secrets**, configure os três valores mostrados em `.streamlit/secrets.toml.example`.
5. Publique e compartilhe a URL e a senha somente com as pessoas responsáveis pela biblioteca.

As credenciais reais nunca devem ser adicionadas ao GitHub. O Streamlit guarda esses valores separadamente nos Secrets do aplicativo.

## Dados

O banco é criado automaticamente em:

```text
data/biblioteca.db
```

Faça backup desse arquivo periodicamente, pois ele contém todos os cadastros e movimentações.
Na barra lateral há o botão **Backup do banco (.db)** para baixar uma cópia a qualquer momento.
