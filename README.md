# PetAgenda Pro

Sistema web/PWA para pet shop de banho e tosa.

## O que já vem pronto

- Login com usuário administrador
- Dashboard do dia
- Cadastro de tutores/clientes
- Cadastro de pets com foto, porte, raça, observações e restrições
- Cadastro de serviços com duração e preço
- Cadastro de pacotes mensais por serviço, quantidade, validade e preço
- Controle de pacotes por tutor/pet com saldo consumido pela agenda
- Agenda com cálculo automático do horário final
- Bloqueio de conflitos de horário
- Bloqueio manual de agenda
- Controle de status do atendimento
- Registro de pagamento
- Financeiro simples por período
- Botões de WhatsApp com mensagem pronta
- PWA instalável no celular

## Primeiro acesso

- E-mail: `admin@petagenda.local`
- Senha: `admin123`

Depois do primeiro acesso, crie outro usuário em **Configurações > Usuários** e use uma senha própria.

## Como rodar no Windows

1. Instale o Python 3.11 ou superior.
2. Extraia o ZIP em uma pasta simples, por exemplo: `C:\petagenda_pro`.
3. Dê dois cliques em `start.bat`.
4. Aguarde instalar as dependências.
5. Acesse no navegador: `http://127.0.0.1:5000`.

## Como rodar no Linux/Mac

```bash
cd petagenda_pro
chmod +x start.sh
./start.sh
```

Depois acesse:

```text
http://127.0.0.1:5000
```

## Rodando manualmente

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
set FLASK_APP=run.py      # Windows CMD
# ou
export FLASK_APP=run.py   # Linux/Mac

flask init-db
python run.py
```

## Banco de dados

Por padrão, o sistema usa SQLite local no arquivo:

```text
instance/petagenda.db
```

Para usar PostgreSQL, crie um arquivo `.env` com:

```text
DATABASE_URL=postgresql://usuario:senha@localhost:5432/petagenda
SECRET_KEY=uma-chave-secreta
```

## Deploy

Para colocar online, recomenda-se usar Render, Railway, VPS ou outro serviço com Python. O comando de produção pode ser:

```bash
gunicorn run:app
```

Antes de abrir ao público, configure:

- `SECRET_KEY` forte
- `DATABASE_URL` do PostgreSQL
- HTTPS no domínio
- Backup do banco
