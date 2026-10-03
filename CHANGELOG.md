# Changelog

## 1.21.3 — 2026-10-03
- **Cartões: mais área útil.** Em cada conta de cartão o cartão **principal** fica como cabeçalho e os **adicionais** ficam num bloco "Adicionais (n)" que abre e fecha (começa fechado), junto do botão de adicionar cartão.
- **Faturas em ordem crescente de vencimento** (da mais antiga para a mais nova).

## 1.21.2 — 2026-10-03
- **Cartões: detalhe da fatura mais fácil de conferir.** Ao abrir uma fatura, as compras agora são agrupadas primeiro por **cartão (final)** e, dentro dele, por **data da compra**, como no extrato do banco, cada nível com o seu subtotal. É possível recolher/expandir a fatura, cada cartão e cada data, e há os atalhos **Expandir tudo**, **Recolher tudo** e **Só cartões**. Só a tela mudou; a API é a mesma.

## 1.21.1 — 2026-10-03
- **Início: o Total agora bate com a linha de baixo.** O quadro de posição (Disponível, Benefícios, Subtotal, Investimento, Outros e Total) passa a **incluir o que ainda vai entrar no período** (salário, recargas de benefício, rendimentos previstos). Assim o Total é exatamente **Saldo + A receber + A pagar + Faturas**. Antes o quadro deixava o "A receber" de fora, e a diferença crescia a cada mês a mais escolhido. O mesmo vale para o valor de cada conta na lista de Contas. Os dados da API não mudam: `livre` continua sendo o valor sem as entradas e `projetado` é o que a tela mostra.

## 1.21.0 — 2026-10-03
- **⚠ Ação necessária: a leitura por IA agora é liberada por pessoa.** Ao atualizar, **ninguém (exceto o administrador do `ADMIN_EMAIL`) tem a IA do servidor**; quem já usava deixa de usar até você liberar. Em **Mais › Administração**, cada pessoa tem o botão **IA do servidor: desligada/liberada**. Novas contas também nascem desligadas (o aviso de cadastro chega no seu e-mail).
- **Chave própria do Google.** Em **Mais › Meu perfil › Leitura por IA** cada pessoa pode cadastrar a sua chave do Gemini (com um passo a passo para criá-la no Google AI Studio). O app testa a chave ao salvar, guarda-a **cifrada** (só a própria pessoa a usa; ela nunca volta para a tela, só os 4 últimos caracteres) e, com chave própria, **não há limite diário**. O `CAPTURAS_POR_DIA` vale só para quem usa a chave do servidor. Não há cota mensal nem pedido de liberação.
- **Sem IA, o app continua útil.** Na aba Capturar a foto é guardada como comprovante e o lançamento é feito à mão (a tela explica o motivo). A **importação de fatura em PDF fica indisponível** sem IA, com aviso na tela de Cartões.
- **Administração:** além do botão de liberar, a lista mostra se a pessoa tem chave própria e quantas leituras do mês saíram da chave do servidor.
- Novas rotas: `GET /api/ia`, `PUT/DELETE /api/ia/chave`, `POST /api/admin/usuarios/{id}/ia`. Migração `014` (colunas e tabela novas; todos começam desligados). Nova dependência no servidor: `cryptography`.

## 1.20.0 — 2026-10-03
- **Administração: uso de IA e média de lançamentos por pessoa.** A lista de pessoas passa a mostrar quantas **leituras por IA** (comprovantes e faturas) cada uma fez, no total e nos últimos 30 dias, e a **média mensal de lançamentos** que ela criou (últimos 3 meses, sem contar recorrências e rendimentos gerados sozinhos). São apenas contagens; continua sem mostrar lançamentos, valores, descrições ou nomes de contas. A contagem de IA inclui o histórico anterior à atualização. Migração `013` (só troca a função de relatório).

## 1.19.0 — 2026-10-03
- **Nova barra de navegação.** **Investimentos** ganhou uma aba própria na barra de baixo (Início, Lançamentos, Capturar, Cartões e Investimentos). Quem ainda não tem conta de investimento vê a tela vazia, com a orientação de como criar uma. O atalho para **Mais** virou um ícone ☰ no canto superior direito de todas as telas (menos nas do próprio Mais e no formulário de novo lançamento). As Premissas passam a ficar em Investimentos › Premissas.
- **Aviso de novo cadastro vai para o `ADMIN_EMAIL`.** O e-mail de aviso a cada conta nova deixa de ir para o `SMTP_USER` e passa a ir para o e-mail do administrador (`ADMIN_EMAIL`). Com `ADMIN_EMAIL` vazio, nada é enviado.

## 1.18.0 — 2026-10-03
- **Tela de Investimentos com evolução, cenários e simulador.** Em **Mais › Investimentos** aparece o **Patrimônio investido** com um gráfico: linha cinza com o saldo real dos últimos 12 meses e a **projeção** (12 meses, 2, 5 ou 10 anos) em três cenários, **base** e **pessimista/otimista**, que deslocam Selic, CDI e IPCA em 2 pontos percentuais. A tabela mostra o saldo projetado bruto e o **líquido de IR estimado** no cenário base. Há também a **alocação por tipo** de investimento e o **simulador**: aporte hoje, aporte mensal, resgate único e prazo, sobre uma das suas contas ou sobre uma taxa anual informada, comparando com "não mudar nada". Tudo é estimativa a partir das suas premissas, não recomendação de investimento. Novas rotas: `GET /api/investimentos/painel` e `POST /api/investimentos/simular`.

## 1.17.0 — 2026-10-03
- **Contas de investimento com subtipo, rendimento e vencimento.** A **poupança deixou de ser um tipo de conta**: ela agora é um subtipo de **Investimento** (contas de poupança que você já tinha foram convertidas, sem mudar saldo nem lançamentos). Cada investimento tem subtipo (poupança, Tesouro Selic, Prefixado e IPCA+, CDB, LCI, LCA, LC, LA, debêntures, CRI/CRA, fundo de renda fixa, previdência, renda variável, outro), forma de rendimento (prefixado, % do CDI, Selic + taxa, IPCA + taxa ou poupança), data da aplicação, **dia de aniversário** e **data de vencimento** opcional.
- **Rendimento previsto.** O app estima o rendimento dos próximos 6 meses e cria lançamentos **previstos** de receita no dia de aniversário (usando o saldo e os aportes/resgates previstos). Confirme com o valor real do extrato e as estimativas seguintes se refazem. O último período termina no vencimento. Em **Mais › Investimentos** aparecem o saldo, o próximo rendimento bruto e o **líquido estimado** (IR regressivo da renda fixa, 22,5% a 15%; poupança, LCI, LCA e debêntures incentivadas isentas por padrão, editável).
- **Premissas manuais.** Selic, CDI, IPCA e TR esperados são definidos por você em Mais › Investimentos › Premissas (os valores iniciais são exemplos). O app não busca nada na internet.
- **Renda variável e previdência** entram como valor informado por você: o botão **Atualizar valor** lança a diferença como ganho ou perda.
- **Alerta de vencimento.** O vencimento aparece nos Próximos eventos (só para o dono) e o dono recebe **um e-mail** quando faltam até N dias (padrão 30, configurável por investimento). Tudo é estimativa para planejamento, não recomendação de investimento.

## 1.16.1 — 2026-10-02
- **Início: padrão é o mês atual.** Quando o aparelho ainda não tem um período guardado, o quadro de posição e os Próximos eventos mostram **só este mês** (antes era este e o próximo). Quem já escolheu outro período continua com a sua escolha.

## 1.16.0 — 2026-10-02
- **Recorrências aparecem nos meses seguintes.** O app agora cria sozinho os lançamentos **previstos** de cada recorrência para o mês atual e os 5 seguintes (uma janela que anda, nunca infinita). Com isso eles entram no Disponível, nos Próximos eventos, nas faturas de cartão e no orçamento dos períodos de 2, 3 e 6 meses. Na lista de Lançamentos eles ganham a marca "↻ recorrente".
- **Edição e exclusão com alcance à sua escolha.** Ao excluir um lançamento recorrente: **só este mês** (pula o mês) ou **este e os próximos** (a recorrência termina no mês anterior e os previstos dali em diante saem). Ao editar um lançamento previsto de recorrência, a opção **Aplicar também aos meses seguintes** muda a recorrência e refaz os previstos seguintes. Ao excluir a recorrência, você escolhe entre remover também os previstos ou **mantê-los como lançamentos avulsos**. O que já foi confirmado nunca é apagado. Editar ou pausar uma recorrência passa a completar os previstos até o horizonte.

## 1.15.0 — 2026-10-02
- **Início: período por meses fechados.** O quadro de posição (Disponível, Benefícios, Total...) e os **Próximos eventos** deixam de usar "próximos N dias" e passam a usar meses completos: **só este mês**, **este mês e o próximo** (novo padrão), **este mês e os 2 seguintes** ou **este mês e os 5 seguintes**, sempre até o último dia do mês final (o título mostra a data, por exemplo "Posição até 30/11"). Assim o número não muda só porque o dia passou. O que está atrasado continua entrando na conta, e a escolha fica lembrada no aparelho. As rotas de saldo e de lembretes ganharam o parâmetro `ate` (data final); o parâmetro `dias` continua funcionando.

## 1.14.0 — 2026-10-02
- **Área de administração (opcional, somente leitura).** Preenchendo `ADMIN_EMAIL` no `docker-compose.yml`, quem entra com esse e-mail vê **Mais › Administração**: lista de pessoas cadastradas com data de cadastro, último acesso e número de contas e cartões ativos de que cada uma é dona. Não mostra lançamentos, valores nem nomes de contas. Com `ADMIN_EMAIL` vazio (padrão), ninguém tem acesso e a área nem aparece; instalações existentes não mudam nada.
- **"Pagador" nas receitas.** Nos formulários de lançamento e de recorrência, o campo que se chama "Favorecido" passa a se chamar **Pagador** quando o lançamento é uma receita.

## 1.13.6 — 2026-10-02
- **Compra no cartão não tem mais "previsto".** Ao lançar (à mão ou pela leitura de notas) numa conta de cartão, a opção "Ainda não aconteceu (previsto)" some e o formulário avisa que a compra só sai do saldo quando a fatura for paga. O servidor também ignora esse pedido para cartões. As parcelas futuras continuam sendo criadas como previstas pelo próprio app, e confirmar uma parcela prevista segue funcionando.

## 1.13.5 — 2026-10-01
- **Faturas vazias não ficam mais abertas.** Ao excluir lançamentos (um ou vários), as faturas de cartão que ficaram sem nenhuma compra, abertas e sem pagamento são removidas automaticamente. Faturas vazias que já existiam também somem ao abrir **Cartões**. Faturas pagas ou com pagamento vinculado nunca são removidas; se uma compra nova cair no mês, a fatura é recriada sozinha.

## 1.13.4 — 2026-10-01
- **Importar fatura: leitura corrigida.** A IA estava confundindo os ícones da coluna "Compra" da fatura (pagamento por aproximação e "@" de compra online) com parcelas, marcando compras à vista como "1/3" ou "1/2" e criando parcelas futuras indevidas. O pedido à IA agora diz que só vale a parcela escrita na coluna Parcela. Além disso, se muitas compras novas de uma fatura vierem como parceladas 1/x, a conferência mostra um alerta e **deixa desmarcada** a criação das parcelas futuras.
- **Selecionar vários lançamentos e excluir.** Em Lançamentos, o botão **Selecionar** liga a seleção: marque linhas uma a uma, use **Marcar todas** (vale para tudo o que o filtro mostra) e **Excluir marcadas**. Para parcelas há a opção de excluir também as demais parcelas (inclusive as futuras) dos parcelamentos marcados. O que não puder ser excluído (conciliado ou sem permissão) fica de fora e é avisado; o resto é excluído. Dica para limpar uma importação errada: filtre por cartão e por "Só previstos" e marque tudo.

## 1.13.3 — 2026-10-01
- **Corrige a importação de fatura nova com parcelas antigas.** Quando a fatura ainda não existia no app, o destino era escolhido pela data da compra mais antiga da lista (por exemplo, uma parcela de 2025) e a gravação falhava com "o vencimento da fatura não bate com o do app". Agora o destino vem sempre do **vencimento do PDF**.

## 1.13.2 — 2026-10-01
- **Importar fatura: valores sem confusão.** A conferência mostra os valores como na fatura do banco (compras positivas; créditos e estornos aparecem como "crédito −R$ …") e a diferença de valor vem em texto ("R$ 4,33 a mais na fatura"). Ao gravar, nada muda: cada compra continua entrando como despesa do cartão.
- **Importar fatura: categorias.** A IA agora sugere a categoria de cada compra (quando a loja ainda é nova para você), além do que o app já sabia pelo histórico e pelo favorecido. Ao trocar a categoria de uma linha, as outras linhas da mesma loja acompanham. Depois de gravar, o app aprende a categoria de cada favorecido, então nas próximas faturas a maioria já vem preenchida.

## 1.13.1 — 2026-10-01
- **Importar fatura: parcelas futuras.** Nas compras parceladas novas da fatura (ex.: 3/10), a conferência traz a opção, marcada por padrão, de **criar também as parcelas seguintes como previstas** nas faturas dos meses certos (ex.: "7 × R$ 100,00, até 05/2027"). A fatura que está sendo importada não muda de total; o "Disponível" e as faturas futuras passam a enxergar o compromisso. Parcelas que já existem (lançadas à mão ou numa importação anterior) não são duplicadas. Ao importar a fatura seguinte, a parcela prevista que casar passa a **confirmada** (e, se o valor mudar, a diferença aparece na conferência).

## 1.13.0 — 2026-10-01
- **Importar fatura do cartão (PDF):** em Cartões, na conta de cartão, o botão **Importar fatura (PDF)** lê a fatura com a mesma IA dos comprovantes (é preciso ter a chave do Gemini configurada). Se o PDF tiver senha, informe-a na hora: ela abre o arquivo só em memória e não é guardada. Antes de gravar, o app mostra uma tela de conferência: o que já estava lançado (e, quando o valor ou a data diferem, a **diferença**, para você escolher entre usar o da fatura ou manter o do app), o que é novo (com favorecido e categoria sugeridos, editáveis), o que não é compra (pagamentos, encargos) e o que está no app mas não apareceu na fatura. Também compara o total da fatura com a soma das compras lidas. Cada cartão (titular e adicionais, pelo final) recebe suas compras; parcelas entram como a parcela da fatura (ex.: 3/10) e o IOF de compras no exterior é somado à compra. Só o dono da conta de cartão importa, e importar de novo a mesma fatura não duplica nada.

## 1.12.0 — 2026-10-01
- **Aviso de novo cadastro:** sempre que uma conta nova é criada (primeiro acesso de um e-mail), o e-mail configurado em `SMTP_USER` recebe uma mensagem com o endereço de quem entrou e a data e hora. Acessos seguintes da mesma pessoa não geram aviso. Não há nada a configurar (migração 009, só adiciona uma função, aplicada sozinha).

## 1.11.0 — 2026-10-01
- **Atenção ao atualizar:** a porta padrão passou de **8000** para **8472**, para não conflitar com outros aplicativos comuns (como o Portainer). O app agora escuta na 8472 também dentro do container, então **baixe o `docker-compose.yml` novo** (linha `"8472:8472"`) antes do `docker compose pull && docker compose up -d`, ou ajuste a sua. Atualize também o `APP_URL` e qualquer proxy, túnel ou domínio que apontava para a 8000. Para manter outra porta, mude só o número da esquerda em `ports` (ex.: `"8080:8472"`).

## 1.10.0 — 2026-10-01
- Ao efetivar um pagamento, recebimento ou transferência (no Início ou no detalhe do lançamento), um pop-up pede o **valor real** e a **data em que aconteceu**, para casar com o extrato do banco (útil em contas de valor variável, como luz). A sugestão de data é a prevista se já passou, ou hoje se ainda for futura; a competência não muda. O botão "Só ajustar a previsão" corrige valor e data sem efetivar, inclusive em transferências previstas (as duas pontas). Compras no cartão seguem o vencimento da fatura.
- Tela **Lançamentos** com **filtros**: período (mês ou intervalo livre, por competência ou caixa), conta ou cartão (com plástico/portador e fatura), favorecido, categoria (a principal inclui as subcategorias), tipo, situação e busca por texto em descrição, favorecido e categoria. Os filtros ativos viram chips removíveis, os totais refletem a seleção inteira e "Ver por categoria e favorecido" detalha onde o dinheiro foi (toque para filtrar). Serve também para consultar compras do cartão.
- **Sugestões de favorecido** ao preencher o campo (novo lançamento, edição, confirmação de nota capturada, recorrência e filtro): ao tocar no campo aparecem os mais usados; ao digitar, os que começam com o texto vêm primeiro (ignora acentos). Escolher uma sugestão também sugere a categoria padrão dela.
- **Editar recorrências** (Mais → Lançamentos recorrentes, toque na recorrência): valor, dia, favorecido, categoria, forma de pagamento e data final. Escolha se a mudança vale deste mês em diante ou só a partir do próximo: os previstos do período são refeitos, o que já foi confirmado não muda e não há duplicidade no mês. Também dá para **pausar** (remove os previstos futuros e para de gerar) e reativar.
- **Próximos eventos agrupados por data** no Início: um grupo para os atrasados e um por dia, cada um com a quantidade de eventos e o total. Atrasados e hoje começam abertos; toque no grupo para recolher ou expandir, ou use "Expandir tudo"/"Recolher tudo". Os grupos mantêm o estado ao confirmar um evento.
- **Resumo do mês navegável** no Início: setas ‹ › para ver outros meses (e "Voltar para o mês atual"). O botão "Ver orçamento do mês" abre o orçamento no mês que você está olhando.
- **Excluir uma ocorrência de recorrência = pular aquele mês**: ao excluir um lançamento que veio de uma recorrência, o app pergunta se é só este mês e passa a não recriá-lo; os outros meses seguem. Na edição da recorrência há a lista de "Meses pulados" com "Voltar a valer" (migração 008, só adiciona uma tabela e é aplicada sozinha).
- **Primeira cobrança** ao criar uma recorrência: "Este mês" ou "Próximo mês". Se o dia deste mês já chegou, a sugestão é o próximo mês, porque o valor costuma já estar no saldo.

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
