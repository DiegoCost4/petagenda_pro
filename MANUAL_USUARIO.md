# Manual de Uso - PetAgenda Pro

> Para atualizar uma instalação existente, leia [UPGRADE.md](UPGRADE.md) e faça um backup validado antes de iniciar a versão nova.

## 1. Objetivo do sistema

O PetAgenda Pro foi criado para controlar a rotina de uma pet shop de banho e tosa pelo celular. Ele permite cadastrar tutores, pets, serviços, agendamentos, pagamentos e acompanhar o status de cada atendimento.

## 2. Primeiro acesso

Abra o sistema no navegador e faça login com:

- E-mail: `admin@petagenda.local`
- Senha: `admin123`

Depois, acesse **Configurações > Usuários** e crie um usuário próprio.

## 3. Tela inicial

A tela inicial mostra:

- Agendamentos do dia
- Valor previsto do dia
- Valor recebido no dia
- Quantidade de clientes e pets cadastrados
- Próximo atendimento
- Atalhos rápidos

Use essa tela como painel principal da rotina diária.

## 4. Cadastro de tutores

O tutor é o dono/responsável pelo pet.

Caminho:

```text
Menu inferior > Tutores > Novo tutor
```

Preencha:

- Nome
- Telefone/WhatsApp
- E-mail, se houver
- Endereço, se quiser
- Observações gerais

Na tela do tutor, você consegue:

- Ver os pets cadastrados
- Abrir WhatsApp
- Criar novo pet
- Criar novo agendamento
- Ver histórico de agendamentos

## 5. Cadastro de pets

Caminho:

```text
Menu inferior > Pets > Novo pet
```

Preencha:

- Tutor responsável
- Nome do pet
- Espécie
- Porte
- Raça
- Sexo
- Idade
- Peso
- Foto, se quiser
- Observações de comportamento
- Restrições ou cuidados especiais

Exemplos de observações úteis:

- Tem medo de secador
- Pode morder
- Usar shampoo neutro
- Possui alergia
- Tutor prefere tosa baixa

## 6. Cadastro de serviços

Caminho:

```text
Dashboard > Serviços e preços
```

Cadastre os serviços com duração e valor.

Exemplos:

- Banho pequeno - 60 minutos - R$ 50,00
- Banho médio - 90 minutos - R$ 70,00
- Banho grande - 120 minutos - R$ 100,00
- Banho + Tosa pequeno - 120 minutos - R$ 90,00
- Tosa higiênica - 45 minutos - R$ 40,00

A duração é importante porque o sistema usa esse tempo para calcular o horário final e evitar conflitos de agenda.

## 7. Criar novo agendamento

Caminho:

```text
Botão + no menu inferior
```

Ou:

```text
Agenda > Novo agendamento
```

Passo a passo:

1. Selecione o tutor.
2. Selecione o pet.
3. Selecione o serviço.
4. Escolha a data.
5. O sistema mostrará os horários livres.
6. Escolha o horário.
7. Confira o valor.
8. Salve.

O sistema calcula automaticamente o horário final com base na duração do serviço.

Exemplo:

- Serviço: Banho + Tosa pequeno
- Duração: 120 minutos
- Horário escolhido: 09:00
- Horário final calculado: 11:00

## 8. Status do atendimento

Cada agendamento pode ter os seguintes status:

- Agendado
- Confirmado
- Em atendimento
- Pronto
- Entregue
- Cancelado
- Faltou

Sugestão de uso:

1. Quando marcar: **Agendado**
2. Quando o cliente confirmar: **Confirmado**
3. Quando o pet chegar: **Em atendimento**
4. Quando terminar: **Pronto**
5. Quando entregar e receber: **Entregue**

## 9. WhatsApp

Na tela do agendamento existem dois botões:

- Confirmar agendamento
- Avisar que está pronto

O sistema abre o WhatsApp com a mensagem pronta. Basta revisar e enviar.

## 10. Pagamento

Na tela do agendamento, clique em **Marcar como pago**.

Você pode registrar:

- Pix
- Dinheiro
- Cartão de débito
- Cartão de crédito

Quando marcar como pago, o financeiro passa a considerar esse valor como recebido.

## 11. Financeiro

Caminho:

```text
Dashboard > Financeiro
```

A tela mostra:

- Valor previsto no período
- Valor recebido
- Valor pendente
- Lista de atendimentos
- Lista de hospedagens e valores do hotelzinho
- Recebimentos por forma de pagamento

Use os filtros de data para ver o dia, semana ou mês.

O botão **Ocultar valores** no cabeçalho esconde os valores monetários exibidos na tela. Use **Mostrar valores** para exibi-los novamente; a escolha fica salva neste navegador.

## 12. Configurar horários de funcionamento

Caminho:

```text
Configurações > Horários de funcionamento
```

Configure para cada dia:

- Horário inicial
- Horário final
- Pausa, se houver
- Se o dia está ativo ou não

Exemplo:

- Segunda a sexta: 08:00 às 18:00
- Sábado: 08:00 às 14:00
- Domingo: inativo

## 13. Bloquear horários

Use bloqueios para folgas, almoço, consultas ou horários indisponíveis.

Caminho:

```text
Configurações > Novo bloqueio de agenda
```

Preencha:

- Data
- Hora inicial
- Hora final
- Motivo

O sistema não deixará criar agendamento em horário bloqueado.

## 14. Instalar como aplicativo no celular

No Android/Chrome:

1. Abra o sistema no Chrome.
2. Toque nos três pontinhos.
3. Toque em **Adicionar à tela inicial** ou **Instalar app**.
4. Confirme.

No iPhone/Safari:

1. Abra o sistema no Safari.
2. Toque no botão de compartilhar.
3. Toque em **Adicionar à Tela de Início**.
4. Confirme.

## 15. Rotina recomendada no dia a dia

1. Abra o sistema pela manhã.
2. Veja a tela inicial.
3. Confirme os agendamentos pelo WhatsApp.
4. Quando o pet chegar, altere para **Em atendimento**.
5. Quando terminar, altere para **Pronto**.
6. Avise o tutor pelo WhatsApp.
7. Ao receber, marque como pago.
8. No fim do dia, veja o financeiro.

## 16. Backup

Se estiver usando SQLite local, faça cópia frequente da pasta:

```text
instance/petagenda.db
```

Esse arquivo contém os dados do sistema.

Se colocar online com PostgreSQL, configure backup automático no servidor ou plataforma.

## 17. Pacotes mensais e renovações

Em **Pacotes**, vincule um pacote ao pet. A primeira vigência é mensal: começa na data escolhida e termina no dia anterior ao próximo aniversário do contrato. Os créditos não se acumulam entre ciclos.

Quando um ciclo vence, ele aparece automaticamente em **Renovações > Pendentes**. Confira o tutor, pet, consumo e valor. Use **Aprovar** para criar outro ciclo ou **Não renovar** para encerrar sem liberar créditos. Ambas as decisões pedem confirmação. As abas de histórico mostram quem decidiu e quando.

Na página do pacote do pet, **Renovar pacote antecipadamente** encerra o ciclo atual e cria outro começando no dia da confirmação. A mensagem informa os créditos que expiram e as novas datas. Agendamentos futuros já vinculados ao ciclo antigo precisam ser resolvidos antes dessa ação.

Use **Agendar com este pacote** para abrir a agenda com tutor, pet, serviço e pacote já selecionados. O crédito é reservado quando o agendamento é salvo. Cancelar ou marcar falta libera o saldo apenas enquanto o ciclo ainda permite uso.

## 18. Hotelzinho

Em **Hotelzinho > Configurar diária**, informe o valor padrão por pet. O valor é copiado para cada nova hospedagem e alterações futuras não mudam os registros anteriores.

Em **Nova hospedagem**, selecione um tutor e um ou mais pets dele, entrada e saída, diária e desconto. A saída deve ser posterior à entrada. O sistema usa a diferença de datas como quantidade de pernoites e calcula subtotal, desconto e total. Ele impede períodos sobrepostos para o mesmo pet.

Na listagem, busque por tutor ou pet e filtre por período. Abra uma hospedagem para editar antes do check-in, cancelar, registrar entrada ou registrar saída. O histórico da hospedagem guarda essas ações. As páginas do tutor e do pet também mostram seus registros de hotelzinho.

Na hospedagem, registre a data e a forma de pagamento para incluir o total como recebido no financeiro. Antes disso, o valor aparece como previsto pela data de entrada. É possível estornar um pagamento registrado; para cancelar uma hospedagem paga, estorne primeiro.

## 19. Uso em tablet

Os módulos principais ficam no topo em tablets e computadores. Em celulares, use o menu de módulos no cabeçalho e a barra inferior para as ações mais frequentes. A interface funciona nas orientações vertical e horizontal.
