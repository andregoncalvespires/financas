# Finanças

**Português (Brasil)** · [Português (Portugal)](README.pt-PT.md) · [English](README.en.md)

Aplicativo de finanças pessoais e da família, **auto-hospedado**: você instala no seu próprio computador ou servidor, os dados ficam com você, e várias pessoas podem usar com privacidade. Funciona no navegador e pode ser instalado no celular como aplicativo (PWA).

## Instalação em 3 passos

Você só precisa do **Docker** com Compose (Docker Desktop no Windows e no macOS; Docker Engine no Linux).

**1. Baixe o arquivo modelo.** Crie uma pasta e salve nela o [`docker-compose.yml`](https://raw.githubusercontent.com/andregoncalvespires/financas/main/docker-compose.yml). Em um terminal:

```bash
mkdir financas && cd financas
curl -fsSLO https://raw.githubusercontent.com/andregoncalvespires/financas/main/docker-compose.yml
```

**2. Preencha duas linhas.** Abra o `docker-compose.yml` em um editor de texto e preencha, no bloco "EDITE AQUI" no topo, `SMTP_USER` (o seu e-mail) e `SMTP_PASSWORD` (a senha do e-mail). É por esse e-mail que o app envia os códigos de acesso.

<details>
<summary><b>Usa Gmail? Como obter a senha (1 minuto)</b></summary>

1. Na sua conta Google, ative a **verificação em duas etapas** (Conta Google → Segurança).
2. Abra <https://myaccount.google.com/apppasswords> e crie uma **senha de app**. O Google mostra 16 letras: copie sem os espaços.
3. No `docker-compose.yml`:
   ```yaml
   SMTP_USER: "seu.nome@gmail.com"
   SMTP_PASSWORD: "abcdefghijklmnop"
   ```
</details>

**3. Inicie e abra.**

```bash
docker compose up -d
```

Abra <http://localhost:8472>, digite o seu e-mail, informe o código que chegou na caixa de entrada e pronto. Na primeira execução o app gera sozinho as senhas internas (banco de dados e segurança); você não precisa criar nem anotar nada.

Para usar de outro aparelho da mesma rede (celular, tablet), abra `http://IP-DO-COMPUTADOR:8472`.

Se algo não funcionar, veja [Problemas comuns](#problemas-comuns).

## Telas

> Prefere um passo a passo para quem vai só usar o app? Há um **[guia do usuário em PDF](docs/Guia-do-usuario.pdf)**, sem detalhes técnicos de instalação.

<p align="center">
<img src="docs/img/01-inicio.png" width="180" alt="Início"> <img src="docs/img/02-proximos-eventos.png" width="180" alt="Próximos eventos"> <img src="docs/img/05-lancamentos.png" width="180" alt="Lançamentos"> <img src="docs/img/06-filtros.png" width="180" alt="Filtros"> <img src="docs/img/07-filtro-cartao.png" width="180" alt="Consulta por cartão"> <img src="docs/img/08-cartoes.png" width="180" alt="Cartões e faturas"> <img src="docs/img/09-investimentos.png" width="180" alt="Investimentos: evolução e cenários"> <img src="docs/img/10-investimentos-aloc.png" width="180" alt="Alocação e contas de investimento">
</p>

<sub>Dados fictícios, apenas para demonstração.</sub>

## O que o aplicativo faz

**Contas e saldos**
- Contas correntes, investimentos, dinheiro em espécie, contas de terceiros e **benefícios** (vale-refeição, vale-alimentação) com **recarga mensal** automática, que você pode ajustar ou desativar. Você cria seus próprios **tipos de conta**.
- **Saldo disponível calculado**: saldo atual mais o que está previsto para entrar, menos o que está previsto para sair (contas a pagar, faturas e transferências planejadas) nos meses escolhidos (só este mês, este e o próximo, 3 ou 6 meses, sempre até o fim do mês), e a escolha fica lembrada no aparelho.

**Investimentos**
- Contas de investimento com **subtipo** (poupança, Tesouro Selic, Prefixado e IPCA+, CDB, LCI, LCA, LC, LA, debêntures, CRI/CRA, fundos de renda fixa, previdência e renda variável), taxa de rendimento, **dia de aniversário** e **data de vencimento**.
- O app **estima o rendimento** dos próximos meses (cria lançamentos previstos de receita no dia de aniversário); quando o extrato chegar, você confirma com o valor real e as estimativas seguintes são refeitas. A tela mostra o rendimento bruto e o **líquido estimado** (IR regressivo da renda fixa; poupança, LCI e LCA isentas).
- **Evolução e cenários:** na aba **Investimentos** há um gráfico com o saldo real dos últimos meses e a projeção em três cenários (base, pessimista e otimista, deslocando Selic, CDI e IPCA em 2 pontos), a **alocação por tipo** e um **simulador** de aporte mensal e resgate (sobre uma das suas contas ou sobre uma taxa que você informa).
- **Premissas** (Selic, CDI, IPCA, TR) são definidas por você na aba Investimentos; nada é buscado na internet. Renda variável e previdência entram como **valor informado por você**.
- **Alerta de vencimento** nos Próximos eventos e **e-mail ao dono da conta** antes de vencer (a antecedência é configurável). Tudo é estimativa para planejamento, não recomendação de investimento.

**Lançamentos**
- Despesas, receitas e **transferências entre contas** (da corrente para a poupança, para o dinheiro etc.), que não distorcem as receitas e despesas do mês.
- **Data de competência** (a que mês pertence) e **data de caixa** (quando o dinheiro se move).
- **Previsto ou efetivado**: planeje pagamentos e recebimentos futuros, confirme quando acontecerem ou volte um lançamento para previsto se confirmou por engano. Compras no cartão não têm essa opção: elas entram na fatura e só saem do saldo quando a fatura é paga (as parcelas futuras ficam previstas automaticamente).
- **Selecionar vários e excluir**: em Lançamentos, o botão *Selecionar* permite marcar várias linhas (ou todas as do filtro atual) e excluir de uma vez, inclusive o parcelamento inteiro. O que não puder ser excluído é avisado, e o resto é excluído.
- Nas receitas, o campo que identifica a outra parte aparece como **Pagador** (nas despesas, *Favorecido*).
- **Recorrências** (aluguel, salário, assinaturas): o app cria sozinho os lançamentos previstos do mês atual e dos 5 seguintes, então eles aparecem no Disponível e nos próximos eventos. Ao editar ou excluir você escolhe o alcance: só aquele mês, ou ele e os próximos (o que já foi confirmado nunca é apagado). Também há parcelamentos, favorecidos com categoria sugerida e um plano de categorias enxuto que você edita e pode mesclar.

**Cartão de crédito**
- Faturas com fechamento e vencimento, compras parceladas e pagamento da fatura a partir de uma conta.
- **Importar a fatura em PDF** (com ou sem senha): o app lê as compras, compara com o que você já lançou, mostra as diferenças de valor para você decidir e só grava depois da sua conferência. Requer a leitura por IA ativada.
  - Compras parceladas novas podem criar também as **parcelas seguintes como previstas** nas faturas dos meses certos, sem mudar o total da fatura importada. Na fatura seguinte, a parcela prevista que casar vira confirmada.
  - A IA sugere a categoria de cada compra; se muitas compras vierem como parceladas, a conferência avisa e deixa as parcelas futuras desmarcadas.
  - A senha do PDF é usada só para abri-lo e não é guardada. Quem importa é o dono do cartão.
- Faturas que ficam sem nenhuma compra (por exemplo, depois de excluir lançamentos) e ainda abertas são removidas automaticamente.
- **Cartões adicionais** e virtuais: as compras de todos caem na fatura do titular. Um familiar convidado como portador vê só os próprios gastos.

**Planejamento**
- **Orçamento** por categoria com regras de vigência: sem data final, por número de meses, em meses específicos do ano ou ajuste de um único mês.
- **Navegação**: a barra de baixo tem Início, Lançamentos, Capturar, Cartões e Investimentos; o menu **Mais** (contas, categorias, recorrências, convites, perfil) fica no ícone ☰ no canto superior direito.
- **Início**: resumo por grupos (disponível, benefícios, investimentos, outros e total) e **próximos eventos** (contas a pagar e receber, faturas e transferências planejadas), com botão para confirmar o que já aconteceu.

**Leitura de comprovantes com IA (opcional)**
- Tire uma foto de cupom, nota, comprovante de Pix ou fatura e o app sugere valor, data, estabelecimento e categoria. Você sempre revisa antes de salvar. A leitura por IA é **liberada por pessoa** pelo administrador ou funciona com a **chave própria** de cada um (veja [Leitura de comprovantes com IA](#configurações-opcionais)).

**Várias pessoas, com privacidade**
- Cada pessoa vê apenas os próprios dados. Você compartilha **conta por conta** (ou um cartão) com quem quiser, como leitor, editor ou gestor, e retira o acesso quando quiser.
- **Aviso de novos cadastros:** a cada conta nova, o e-mail do administrador (o `ADMIN_EMAIL` do `docker-compose.yml`) recebe um aviso. Sem `ADMIN_EMAIL` preenchido, nada é enviado.
- **Área de administração** (opcional): com `ADMIN_EMAIL` preenchido, uma pessoa específica vê a lista de cadastrados, o último acesso e quantas contas e cartões cada um tem. Veja [Configurações opcionais](#configurações-opcionais).
- Entrada **sem senha**: um código de 6 dígitos chega por e-mail e o aparelho fica lembrado. Você vê e revoga os aparelhos conectados.
- O isolamento entre pessoas é garantido pelo próprio banco de dados (segurança por linha do PostgreSQL), não só pelo código do aplicativo.

**Seus dados são seus**
- **Exportar tudo** (planilha Excel com lançamentos e faturas, mais os comprovantes) e **excluir a própria conta e todos os dados** a qualquer momento, em Mais → Meu perfil. A tela **Sobre o aplicativo** mostra a versão e as novidades.

> A interface do aplicativo está em português do Brasil.

## Configurações opcionais

<details>
<summary><b>Outro provedor de e-mail (que não seja o Gmail)</b></summary>

Qualquer servidor SMTP que aceite **usuário e senha** serve (um serviço de envio como Brevo, Mailgun ou Amazon SES, ou o servidor de e-mail do seu domínio). No `docker-compose.yml`, tire o `#` e ajuste `SMTP_HOST`, `SMTP_PORT` (587 = STARTTLS, 465 = SSL) e, se quiser, `MAIL_FROM`, com os dados que o provedor informa no painel dele.
</details>

<details>
<summary><b>Área de administração (quem se cadastrou e quando acessou)</b></summary>

Opcional e somente leitura. Preencha `ADMIN_EMAIL: "seu@email.com"` no `docker-compose.yml` e rode `docker compose up -d`. Quem entrar com esse e-mail passa a ver **Mais › Administração**, com a lista de pessoas cadastradas, a data de cadastro, o último acesso e quantas contas e cartões ativos cada uma tem (só os de que ela é dona), quantas **leituras por IA** fez (total e nos últimos 30 dias) e a **média mensal de lançamentos** que criou (últimos 3 meses, sem os gerados sozinhos). São apenas contagens: a área **não mostra lançamentos, valores nem nomes de contas**. Com `ADMIN_EMAIL` vazio (o padrão), a área não existe para ninguém.
</details>

<details>
<summary><b>Leitura de comprovantes com IA (Google Gemini)</b></summary>

Totalmente opcional: sem chave tudo funciona, só a leitura automática fica desligada e você lança manualmente (a foto do comprovante continua sendo guardada; a importação de fatura em PDF, que depende da IA, fica indisponível).

**Quem pode usar a IA:** cada pessoa começa **sem** a leitura por IA. Há dois caminhos, e ambos independem de você mexer no `docker-compose.yml` de novo:
- **IA do servidor** (a `GEMINI_API_KEY` abaixo): o administrador (`ADMIN_EMAIL`) a liga pessoa por pessoa em **Mais › Administração**. O administrador sempre pode usá-la. O limite `CAPTURAS_POR_DIA` vale só para essa chave.
- **Chave própria:** a pessoa cadastra a sua chave do Google em **Mais › Meu perfil › Leitura por IA** (o app testa a chave ao salvar). Ela fica guardada **cifrada**, só a própria pessoa a usa e ela nunca volta para a tela. Com chave própria **não há limite diário**, e o custo é da pessoa.

A área de administração mostra, por pessoa, as leituras por IA (total, últimos 30 dias e quantas saíram da chave do servidor), se há chave própria e o botão de liberar ou desligar a IA do servidor. Ao atualizar para esta versão, **todo mundo (menos o administrador) fica com a IA do servidor desligada**; libere quem quiser.

1. Gere uma chave em <https://aistudio.google.com/apikey>.
2. **Ative o faturamento** no projeto Google dessa chave. Pelos termos da Google, o conteúdo enviado por uma chave sem faturamento (nível gratuito) pode ser usado para melhorar os produtos deles; com faturamento ativo, não. Confira os termos atuais antes de usar com dados reais.
3. No `docker-compose.yml`, preencha `GEMINI_API_KEY: "sua-chave"` e rode `docker compose up -d`.

**O que é enviado ao Google:** apenas a imagem ou o PDF do comprovante (ou da fatura do cartão, já aberto no seu servidor; a senha não é enviada nem guardada) e a lista de categorias do app, para a IA escolher uma. Saldos, contas, nomes e demais lançamentos **não** são enviados. A chave fica só no servidor.

**Como funciona:** a IA devolve uma *sugestão*; você confere, corrige se precisar e só então salva. `CAPTURAS_POR_DIA` (padrão 30) limita o uso diário de quem usa a chave do servidor e controla o custo.
</details>

<details>
<summary><b>Acessar de fora de casa e instalar no celular</b></summary>

O app funciona em qualquer rede onde o computador esteja acessível; ele não depende de nenhum serviço externo. **Como expor para a internet é uma escolha sua** (VPN, túnel, proxy reverso com HTTPS, o que preferir).

- Para **instalar no celular** como aplicativo, o navegador exige HTTPS (ou `localhost`). Sem HTTPS você ainda usa o app normalmente pelo navegador.
- Com HTTPS o app marca o cookie de login como seguro automaticamente. Ajuste `APP_URL` para o endereço público, para os links dos e-mails de convite funcionarem.
- Se usar um proxy, encaminhe para a porta 8472 e envie os cabeçalhos `X-Forwarded-For` e `X-Forwarded-Proto`. Exemplo com Caddy (obtém o certificado sozinho): `financas.seudominio.com { reverse_proxy 127.0.0.1:8472 }`.
- Para aceitar conexões só do próprio computador (por exemplo, atrás de um proxy local), troque a linha `"8472:8472"` por `"127.0.0.1:8472:8472"` no `docker-compose.yml`.

> **Atenção:** qualquer pessoa que alcançar o endereço pode criar uma conta (basta receber o código por e-mail), e o app envia esses e-mails pela sua conta de SMTP. Por isso, mantenha o app na rede local ou proteja o acesso externo. O app limita pedidos de código e de convite por pessoa, mas não substitui essa proteção.
</details>

<details>
<summary><b>Backup e restauração</b></summary>

Seus dados ficam em volumes do Docker (`pgdata`, o banco, e `dados`, os comprovantes). Eles **sobrevivem** a atualizações e reinicializações.

> **Nunca rode `docker compose down -v`**: o `-v` apaga os volumes, ou seja, todos os seus dados. Para parar o app use `docker compose stop` (ou `docker compose down`, sem `-v`).

**Fazer backup** (no Windows, use o WSL ou o Git Bash: o PowerShell altera a codificação dos arquivos gerados):

```bash
docker compose exec -T db pg_dump -U fin_owner -d financas -Fc > financas-$(date +%F).dump
docker compose exec -T api tar czf - -C /data . > comprovantes-$(date +%F).tgz
```

**Guarde esses arquivos fora do computador** (outro disco, nuvem). Para automatizar, coloque os dois comandos no `crontab -e`, com `cd /pasta/do/docker-compose &&` antes.

**Restaurar** (em uma instalação nova ou na mesma, depois de um problema):

```bash
docker compose up -d                  # o app cria a estrutura vazia
docker compose stop api
docker compose exec -T db pg_restore -U fin_owner -d financas --clean --if-exists --no-owner < financas-AAAA-MM-DD.dump
docker compose exec -T api tar xzf - -C /data < comprovantes-AAAA-MM-DD.tgz     # comprovantes (opcional)
docker compose start api
```
</details>

<details>
<summary><b>Atualizar para uma versão nova</b></summary>

Faça um backup (acima) e, na pasta do `docker-compose.yml`:

```bash
docker compose pull
docker compose up -d
```

- Seus dados não são tocados. As mudanças no banco são aplicadas sozinhas na inicialização e **só acrescentam**.
- O `docker-compose.yml` usa `:latest`, que acompanha sempre a versão mais recente. Antes de uma versão principal nova (a 2.0, por exemplo), leia o [CHANGELOG](CHANGELOG.md): ela pode exigir ação sua. Para fixar uma versão, troque por exemplo para `:1.9.0` na linha `x-imagem`.
- Antes de atualizar, leia o [CHANGELOG](CHANGELOG.md): mudanças que exijam alguma ação sua ficam destacadas lá. Em Mais → Sobre o aplicativo você vê a versão em uso e as novidades; se o servidor estiver mais novo que o app aberto no celular, aparece o botão para atualizar.
- **Voltar atrás:** restaure o backup feito antes e use a versão anterior. Voltar só a imagem, sem restaurar o banco, pode não funcionar se a versão nova alterou a estrutura dele.
- Evite ferramentas de atualização automática (como o Watchtower): as mudanças no banco acontecem na inicialização, e um backup antes é importante.
</details>

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O app não inicia (o contêiner `api` reinicia sozinho) | `docker compose logs api`: a primeira linha diz o que falta preencher. |
| O código não chega por e-mail | `docker compose logs api` e procure `e-mail enviado` ou `falha ao enviar`. Causas comuns: senha de app incorreta, verificação em duas etapas desligada, mensagem no spam. |
| Não abre de outro aparelho da rede | Use `http://IP-DO-COMPUTADOR:8472` e libere a porta 8472 no firewall do computador. |
| A porta 8472 já está em uso | No `docker-compose.yml`, troque `"8472:8472"` por `"8080:8472"` e acesse pela porta 8080. |
| Depois de atualizar, o celular mostra a tela antiga | Mais → Sobre o aplicativo → atualizar; se não aparecer, limpe uma vez os dados do site no navegador do celular. |
| A leitura de comprovantes não funciona | Confira `GEMINI_API_KEY` e se o faturamento do projeto Google está ativo; o log mostra o erro retornado. |

## Privacidade e segurança

- Os dados ficam no seu servidor. O único dado que sai dele é o que você escolher enviar: os e-mails de código, convite e aviso de vencimento de investimento (pelo seu provedor de SMTP) e, se ativar a leitura por IA, a imagem do comprovante (para o Google).
- Cada pessoa só enxerga o que é dela ou o que foi compartilhado com ela, e isso é imposto pelo banco de dados.
- Segredos (senhas do banco e chave de proteção dos códigos) são gerados automaticamente e guardados em um volume próprio do Docker.
- Para relatar uma falha de segurança, veja [SECURITY.md](SECURITY.md).

## Remover a instalação

Para desligar o app mantendo os dados: `docker compose down`. Para **apagar tudo definitivamente** (banco, comprovantes e segredos): `docker compose down -v`. Só faça isso com certeza e com um backup guardado.

Cada pessoa também pode excluir a própria conta e os próprios dados em Mais → Meu perfil → *Excluir minha conta e todos os meus dados*, com confirmação por código enviado ao e-mail. Se ela for dona de contas ou cartões compartilhados, eles são apagados para todos, e o app avisa antes quem perde o acesso.

## Para desenvolvedores

Pilha: Python 3.12 (FastAPI), PostgreSQL 16 com segurança por linha, interface em JavaScript puro (PWA, sem etapa de build). As migrações ficam em `backend/migrations` e são aplicadas na inicialização.

```bash
# executar a partir do código-fonte (compila a imagem localmente)
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build

# testes (exigem um PostgreSQL local com o papel fin_owner e o banco financas_test; veja backend/tests/conftest.py)
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
```

Cada versão é uma tag `vX.Y.Z` (o arquivo `VERSION` precisa coincidir): ao criar a tag, o GitHub Actions roda os testes e publica a imagem `ghcr.io/andregoncalvespires/financas`.

## Licença e aviso

Distribuído sob a **GNU Affero General Public License v3.0** ([LICENSE](LICENSE)). Em resumo: você pode usar, estudar, modificar e compartilhar o programa; se oferecer uma versão modificada como serviço a outras pessoas pela rede, deve disponibilizar o código-fonte dela sob a mesma licença. Este resumo não substitui o texto da licença.

Este software é fornecido **como está**, sem garantias, e não constitui aconselhamento financeiro. Mantenha backups dos seus dados.
