# Biblioteca HCI

Sistema local para controlar os livros do endomarketing que ficam disponíveis para empréstimo no escritório.

## O que controla

- Cadastro de livros da biblioteca.
- Cadastro de colaboradores.
- Registro de empréstimos.
- Registro de devoluções.
- Contagem automática de dias com o livro.
- Painel com livros disponíveis, emprestados e maior empréstimo em aberto.
- Histórico exportável em CSV.

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

1. Cadastre os livros em `Livros`.
2. Cadastre os colaboradores em `Colaboradores`.
3. Quando alguém retirar um livro, registre em `Novo empréstimo`.
4. Quando o livro voltar, registre em `Devolução`.
5. Use `Painel` para ver com quem está cada livro.
6. Use `Histórico` para consultar ou baixar as movimentações.

## Dados

O banco é criado automaticamente em:

```text
data/biblioteca.db
```

Faça backup desse arquivo periodicamente, pois ele contém todos os cadastros e movimentações.
Na barra lateral há o botão **Backup do banco (.db)** para baixar uma cópia a qualquer momento.

## Publicar online (Render)

Para os assessores acessarem por um link, sem manter um computador ligado, a forma mais
simples é o [Render](https://render.com). O projeto já inclui o arquivo `render.yaml`, que
configura tudo (inclusive um **disco persistente**, para o banco não se perder a cada deploy).

Passo a passo:

1. Suba este projeto para um repositório no GitHub (pode ser privado).
2. No Render, clique em **New > Blueprint** e selecione o repositório. Ele lê o `render.yaml`.
3. Quando pedir, defina a variável **`BIBLIOTECA_SENHA`** com a senha única que os assessores
   vão usar para entrar. (A `BIBLIOTECA_DB` já vem preenchida.)
4. Conclua a criação. Ao final, o Render dá uma URL pública (ex.: `https://biblioteca-hci.onrender.com`).
5. Compartilhe a URL e a senha com os assessores. Todos usam a **mesma senha** — não é preciso
   cadastrar e-mail de ninguém.

Observações:

- O plano com disco persistente é pago (a partir de ~US$ 7/mês). Ele é necessário: nos planos
  gratuitos o arquivo do banco é apagado a cada reinício, o que faria perder os registros.
- Atualizar o sistema é só dar `git push`; o Render publica a nova versão e mantém o banco.
- **Backup:** o disco do Render não tem backup automático. Baixe o `.db` pelo botão da barra
  lateral de tempos em tempos e guarde em local seguro da empresa.
- **Dados no Brasil:** o `render.yaml` usa datacenter nos EUA. Se houver exigência de manter os
  dados no Brasil, dá para usar outro provedor com região em São Paulo (ex.: Fly.io `gru`) —
  avise que ajusto a configuração.

Para rodar localmente, o app continua funcionando normalmente sem definir nenhuma dessas
variáveis (sem senha e usando `data/biblioteca.db`).
