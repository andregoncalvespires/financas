# Changelog

## 1.9.0 — 2026-09-30
**Atenção ao atualizar (instalações anteriores):**
- O app agora é publicado como **imagem pronta** (`ghcr.io/andregoncalvespires/financas`) e a instalação é um único `docker-compose.yml`, em que você preenche só o bloco "EDITE AQUI" do topo. Atualize com `docker compose pull && docker compose up -d` (faça um backup antes). Seus volumes (banco e comprovantes) continuam valendo. Se você ainda tem um `.env` com `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` e `APP_PEPPER`, esses valores são adotados automaticamente na primeira execução.
- O **envio de e-mail por SMTP é obrigatório** (`SMTP_USER` e `SMTP_PASSWORD` no `docker-compose.yml`) e o modo "console" foi removido. O app não inicia sem isso e o log explica o que falta.
- **Não há mais lista de e-mails nem modo de cadastro**: qualquer pessoa que receba o código no próprio e-mail pode entrar e a conta é criada no primeiro acesso. Para acesso fora da rede local, proteja o endereço (veja o README).
- Deixaram de existir `EMAILS_INICIAIS`, `CADASTRO`, `MAIL_MODE`, `COOKIE_SECURE`, `BIND_ADDR` e as referências ao Cloudflare. O cookie de login passa a ser seguro automaticamente quando o acesso é por HTTPS; para restringir o acesso ao próprio computador, edite a porta no `docker-compose.yml`.

**Novidades**
- Segredos (senhas do banco e `APP_PEPPER`) gerados e guardados automaticamente na primeira execução.
- SMTP com SSL (porta 465) além de STARTTLS (587).
- Limite de 20 convites por pessoa a cada 24 horas.
- Documentação em português do Brasil, português de Portugal e inglês; licença AGPL-3.0.
- Ao efetivar um pagamento, recebimento ou transferência (no Início ou no detalhe do lançamento), um pop-up pede o **valor real** e a **data em que aconteceu**, para casar com o extrato do banco (útil em contas de valor variável, como luz). A sugestão de data é a prevista se já passou, ou hoje se ainda for futura; a competência não muda. O botão "Só ajustar a previsão" corrige valor e data sem efetivar, inclusive em transferências previstas (as duas pontas). Compras no cartão seguem o vencimento da fatura.
- Tela **Lançamentos** com **filtros**: período (mês ou intervalo livre, por competência ou caixa), conta ou cartão (com plástico/portador e fatura), favorecido, categoria (a principal inclui as subcategorias), tipo, situação e busca por texto em descrição, favorecido e categoria. Os filtros ativos viram chips removíveis, os totais refletem a seleção inteira e "Ver por categoria e favorecido" detalha onde o dinheiro foi (toque para filtrar). Serve também para consultar compras do cartão.
- **Sugestões de favorecido** ao preencher o campo (novo lançamento, edição, confirmação de nota capturada, recorrência e filtro): ao tocar no campo aparecem os mais usados; ao digitar, os que começam com o texto vêm primeiro (ignora acentos). Escolher uma sugestão também sugere a categoria padrão dela.
- **Editar recorrências** (Mais → Lançamentos recorrentes, toque na recorrência): valor, dia, favorecido, categoria, forma de pagamento e data final. Escolha se a mudança vale deste mês em diante ou só a partir do próximo: os previstos do período são refeitos, o que já foi confirmado não muda e não há duplicidade no mês. Também dá para **pausar** (remove os previstos futuros e para de gerar) e reativar.
- **Próximos eventos agrupados por data** no Início: um grupo para os atrasados e um por dia, cada um com a quantidade de eventos e o total. Atrasados e hoje começam abertos; toque no grupo para recolher ou expandir, ou use "Expandir tudo"/"Recolher tudo". Os grupos mantêm o estado ao confirmar um evento.

## 1.7.0 — 2026-09-30
- Mais → Sobre o aplicativo: versão em uso, novidades de cada versão e aviso para atualizar quando o servidor tem versão mais nova; versão também na tela de entrada.
- Excluir a própria conta e todos os dados (Meu perfil): confirmação em duas etapas (código por e-mail + digitar EXCLUIR), exclusão imediata. Contas e cartões compartilhados dos quais você é dono são apagados para todos, com aviso prévio. O que você lançou em contas de outras pessoas continua com elas como "Ex-usuário" (migração 007).
- Exportar tudo (planilha + comprovantes) em Meu perfil.

## 1.6.0 — 2026-09-30
- "↩ Voltar para previsto" no detalhe de lançamentos efetivados (com confirmação): desfaz a efetivação mantendo a data; em transferências as duas pontas voltam juntas (recusado se uma ponta não for visível/editável). Bloqueado para conciliados, compras no cartão e pagamento de fatura (para este, excluir reabre a fatura).

## 1.5.1
- Transferências previstas aparecem em Próximos eventos (um evento por transferência, botão "Fiz"); no quadro do Início movem o disponível da origem para o destino sem virar a pagar/a receber.

## 1.5.0
- Transferência entre contas na tela de novo lançamento (prevista ou confirmada); as duas pontas são confirmadas e excluídas juntas; lista mostra "Transferência para/de ..." (sem vazar contas privadas).

## 1.4.0
- Início: resumo por grupos de contas (Disponível, Benefícios, Subtotal, Investimento, Outros, Total) para o período escolhido; removido o "Mostrar reservas"; benefícios voltam ao bloco de contas.
- Próximos eventos (antes "Próximos pagamentos"): período único, faturas por vencimento e valor, próxima fatura de cada cartão mesmo fora do período.
- Orçamento com vigência: sem término, número de meses, meses específicos do ano e ajuste de um mês (migração 006).

## 1.3.3
- Login: o log informa se o código foi gerado ou por que não foi (sem conta / fora de EMAILS_INICIAIS / limite).

## 1.3.2
- E-mail: logs de envio sempre visíveis (`e-mail enviado para ...` / aviso quando MAIL_MODE=console).

## 1.3.1
- Corrige publicação no Git: as migrações SQL (incl. 005) não tinham sido incluídas. A subida agora falha com aviso claro se não houver migrações.

## 1.3.0
- Tipos de conta editáveis (com comportamento) e contas de benefício (ticket/vale) com recarga mensal.
- Cache: arquivos do app sempre revalidam; `BIND_ADDR` no `.env` controla a porta.
## 1.2.0
- Conta de cartão / Cartões (Plástico, Virtual), categorias editáveis, orçamento, lembretes, exportação Excel, competência de parcelados.
## 1.0.0
- Primeira versão: login por código, RLS, contas, cartão, captura com Gemini, saldo disponível.
