# Atualização do PetAgenda Pro

## Antes de atualizar

Pare o serviço e guarde uma cópia do código e dos uploads. Registre a versão anterior para poder voltar a ela. O banco de operação **não foi migrado durante o desenvolvimento**. A aplicação nova exige `flask upgrade-safe` antes do primeiro acesso a um banco existente; a inicialização não migra bancos existentes automaticamente.

### SQLite

Com a versão anterior ainda disponível e o serviço parado:

```powershell
python -m flask --app run.py backup-db backups/petagenda-antes-da-atualizacao.db
python -m scripts.validate_migration instance/petagenda.db
```

`backup-db` usa a API de backup do SQLite, recusa sobrescrita, executa `PRAGMA integrity_check` e imprime SHA256. Guarde o backup fora da pasta de implantação. O validador cria uma cópia temporária, executa o upgrade duas vezes e compara contagens e chaves estrangeiras das tabelas anteriores.

Depois de instalar o código novo e configurar as variáveis de ambiente:

```powershell
python -m flask --app run.py upgrade-safe
python -m flask --app run.py upgrade-safe
python -m unittest discover -s tests -q
```

O segundo upgrade confirma idempotência. Inicie o serviço somente após conferir os comandos. Abra tutores, pets, agendamentos antigos, pacotes e as novas telas de Renovações e Hotelzinho.

### PostgreSQL

Faça um dump consistente com a versão de `pg_dump` compatível com o servidor:

```text
pg_dump --format=custom --file=petagenda-antes-da-atualizacao.dump "$DATABASE_URL"
pg_restore --list petagenda-antes-da-atualizacao.dump
```

Guarde o dump fora do servidor e teste uma restauração em um banco isolado. Aponte `DATABASE_URL` para essa cópia e execute `flask upgrade-safe` e os testes de leitura antes de aplicá-lo ao banco de operação. Não use `flask db migrate` para gerar uma migração automática sobre dados legados.

## Mudanças de esquema

`upgrade-safe` cria `renovacoes_pacote`, `hotel_config`, `hospedagens`, `hospedagem_pets` e `hospedagem_eventos`. Adiciona a `pacotes_clientes` as colunas `contrato_id`, `ciclo_anterior_id`, `tipo_renovacao`, `aprovado_em`, `aprovado_por_id`, `encerrado_em`, `creditos_expirados` e `dia_ancora`, além de um índice único sobre `ciclo_anterior_id`. A coluna antiga `pets.data_aniversario` continua coberta pelo upgrade. Nenhuma linha anterior é convertida, apagada ou renumerada. Cada vínculo legado é interpretado como seu primeiro ciclo; renovações passam a criar novas linhas vinculadas.

Para o financeiro do hotelzinho, o mesmo comando adiciona `pago`, `data_pagamento` e `forma_pagamento` à tabela `hospedagens`. Hospedagens existentes começam como pendentes; nenhum recebimento anterior é presumido.

O vencimento é calculado ao consultar o backend. Não depende de um agendador em execução e não gera créditos sem decisão humana. Para contratos iniciados em 29, 30 ou 31, o aniversário usa o último dia dos meses curtos e recupera o dia original quando possível. Uma renovação antecipada redefine o aniversário para a nova data de início.

## Recuperação

Pare o serviço antes de restaurar. Em SQLite, preserve o banco atual para análise, recoloque o arquivo validado no caminho `instance/petagenda.db` e volte ao código anterior. Em PostgreSQL, restaure o dump em um banco vazio com `pg_restore --clean --if-exists --dbname=<banco_de_recuperacao> ...`, valide esse banco e só então altere `DATABASE_URL` para apontar a ele. Não restaure sobre o banco em uso.

## Limites conhecidos

- A regra atual de agenda considera o crédito consumido quando um agendamento ativo é salvo, inclusive antes da conclusão do serviço. Cancelar ou marcar falta devolve o saldo apenas enquanto o ciclo permitir uso. O registro de uso permanece para auditoria.
- A aplicação não possuía proteção CSRF geral. As novas ações seguem o padrão atual de autenticação e formulários POST; a inclusão de CSRF em todos os módulos deve ser tratada em uma atualização de segurança coordenada.
- A verificação de sobreposição no hotel bloqueia os pets envolvidos no PostgreSQL durante a transação. Para operação SQLite com múltiplos processos gravando simultaneamente, recomenda-se migrar para PostgreSQL.
- Horários reais de check-in e check-out são armazenados e exibidos em UTC.
