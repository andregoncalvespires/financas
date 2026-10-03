import { h, GET, POST, PATCH, PUT_, DEL, brl, folha, aviso, acao, campo, campoFavorecido, limpar, vazio, parseValor, centavosParaCampo, hojeISO, mesISO, somarMes, nomeMes, dataLonga, dataCurta, PAPEIS, FORMAS, confirmar, api } from './util.js';
import { estado, carregarCadastros, destinos } from './form.js';
import { VERSAO_APP } from './versao.js';

const voltar = h_voltar;
function h_voltar(titulo, destino = '#/mais') {
  return h('div', { class: 'topo-sub' }, h('a', { href: destino, class: 'icone', 'aria-label': 'Voltar' }, '‹'), h('h1', null, titulo));
}

export async function mais(raiz, ctx, sub) {
  const telas = { contas, tiposConta, convites, categorias, recorrencias, dispositivos, perfil, sobre, excluirConta, administracao, investimentos, premissas };
  if (sub && telas[sub]) return telas[sub](raiz, ctx);
  let n = 0;
  try { const c = await GET('/api/convites'); n = c.recebidos.length; } catch { /* ignora */ }
  try { await carregarCadastros(); } catch { /* usa o que já tem */ }
  const item = (href, rotulo, extra) => h('a', { class: 'linha item', href }, h('div', { class: 'corpo' }, h('b', null, rotulo)), extra || h('span', null, '›'));
  limpar(raiz).append(h('h1', null, 'Mais'),
    h('div', { class: 'lista' },
      item('#/mais/convites', 'Convites', n ? h('span', { class: 'selo aviso' }, `${n} novo(s)`) : null),
      item('#/mais/contas', 'Contas e compartilhamento'),
      item('#/mais/tiposConta', 'Tipos de conta'),
      item('#/orcamento', 'Orçamento'),
      item('#/mais/categorias', 'Categorias'),
      item('#/mais/recorrencias', 'Lançamentos recorrentes'),
      item('#/mais/dispositivos', 'Dispositivos conectados'),
      item('#/mais/perfil', 'Meu perfil'),
      estado.eu.admin ? item('#/mais/administracao', 'Administração') : null,
      item('#/mais/sobre', 'Sobre o aplicativo', h('span', { class: 'dica' }, `v${VERSAO_APP} ›`))),
    h('button', { class: 'btn sec', onclick: acao(async () => { await POST('/api/auth/sair'); window.dispatchEvent(new Event('sessao-expirada')); }) }, 'Sair deste dispositivo'),
    h('p', { class: 'dica centro' }, estado.eu.email));
}

// ---------- contas ----------
async function contas(raiz, ctx) {
  await carregarCadastros();
  const recarregar = () => contas(raiz, ctx);
  limpar(raiz).append(voltar('Contas'),
    estado.contas.length ? estado.contas.map(c => h('button', { class: 'linha item', onclick: () => detalheConta(c, recarregar) },
      h('div', { class: 'corpo' }, h('b', null, c.nome, c.inativa ? h('small', { class: 'selo aviso' }, 'inativa') : null),
        h('small', null, `${c.tipo_nome || c.tipo} · ${c.dono_id === estado.eu.id ? 'sua' : 'de ' + c.dono_nome + ' (' + (PAPEIS[c.papel] || c.papel) + ')'}`)),
      h('b', null, brl(c.saldo_atual)))) : vazio('Nenhuma conta ainda.'),
    h('button', { class: 'btn', onclick: () => novaConta(recarregar) }, '+ Nova conta'));
}

const CLASSES = [['corrente', 'Conta corrente (entra no disponível)'], ['dinheiro', 'Dinheiro (entra no disponível)'], ['terceiros', 'Terceiros (entra no disponível)'],
  ['investimento', 'Investimento (reserva)'], ['beneficio', 'Benefício: ticket/vale (saldo à parte)']];

function camposRecarga(c) {
  const valor = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0,00', value: c && c.recarga_valor_centavos ? centavosParaCampo(c.recarga_valor_centavos) : '' });
  const dia = h('input', { type: 'number', min: 1, max: 31, placeholder: 'Ex.: 5', value: c && c.recarga_dia ? c.recarga_dia : '' });
  return { valor, dia, vista: [campo('Recarga mensal (R$)', valor, 'O app cria a entrada prevista todo mês; você confirma quando o crédito cair.'), campo('Dia da recarga', dia)] };
}

function novaConta(recarregar) {
  folha('Nova conta', async (corpo, fechar) => {
    const tipos = (await GET('/api/tipos-conta')).filter(t => !t.inativo && t.dono_id === estado.eu.id);
    const nome = h('input', { type: 'text', placeholder: 'Ex.: Itaú corrente' });
    const tipo = h('select', null, tipos.map(t => h('option', { value: t.id }, t.nome)));
    const saldo = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0,00' });
    const data = h('input', { type: 'date', value: hojeISO() });
    const rec = camposRecarga(null);
    const blocoRec = h('div', null, rec.vista);
    let inv = null;                                 // campos de investimento, criados quando o tipo escolhido é de investimento
    const blocoInv = h('div');
    const atualizarRec = async () => {
      const t = tipos.find(x => x.id === tipo.value);
      blocoRec.style.display = (t && t.classe === 'beneficio') ? '' : 'none';
      const ehInv = !!t && t.classe === 'investimento';
      if (ehInv && !inv) { inv = await camposInvestimento(null); blocoInv.append(h('h3', null, 'Investimento'), ...inv.vista); }
      blocoInv.style.display = ehInv ? '' : 'none';
    };
    tipo.addEventListener('change', atualizarRec); atualizarRec();
    corpo.append(campo('Nome', nome), campo('Tipo', tipo, 'Crie outros tipos em Mais › Tipos de conta.'), campo('Saldo inicial (R$)', saldo, 'Saldo real na data abaixo; os lançamentos somam a partir dela.'), campo('Data do saldo inicial', data), blocoRec, blocoInv,
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!nome.value.trim()) throw new Error('Informe o nome.');
        const v = saldo.value.trim() ? parseValor(saldo.value.replace('-', '')) * (saldo.value.trim().startsWith('-') ? -1 : 1) : 0;
        if (Number.isNaN(v)) throw new Error('Saldo inválido.');
        const b = { nome: nome.value.trim(), tipo_conta_id: tipo.value, saldo_inicial_centavos: v, data_saldo_inicial: data.value };
        if (blocoRec.style.display !== 'none' && (rec.valor.value.trim() || rec.dia.value)) {
          const rv = parseValor(rec.valor.value);
          if (Number.isNaN(rv) || rv <= 0 || !(+rec.dia.value >= 1 && +rec.dia.value <= 31)) throw new Error('Confira o valor e o dia da recarga.');
          b.recarga_valor_centavos = rv; b.recarga_dia = +rec.dia.value;
        }
        const tSel = tipos.find(x => x.id === tipo.value);
        const cfgInv = tSel && tSel.classe === 'investimento' && inv ? inv.ler() : null;      // valida antes de criar a conta
        const nova = await POST('/api/contas', b);
        if (cfgInv) await PUT_(`/api/contas/${nova.id}/investimento`, cfgInv);
        fechar(); aviso('Conta criada'); recarregar();
      }) }, 'Criar conta'));
  });
}

// ---------- tipos de conta ----------
async function tiposConta(raiz, ctx) {
  const tipos = await GET('/api/tipos-conta');
  const meus = tipos.filter(t => t.dono_id === estado.eu.id);
  const recarregar = () => tiposConta(raiz, ctx);
  const rotuloClasse = (c) => (CLASSES.find(x => x[0] === c) || [c, c])[1];
  limpar(raiz).append(voltar('Tipos de conta'),
    h('p', { class: 'dica' }, 'Cada tipo tem um nome seu e um comportamento. Reservas ficam fora do disponível; benefícios (ticket/vale) têm saldo à parte.'),
    meus.map(t => h('button', { class: 'linha item', onclick: () => editarTipo(t, recarregar) },
      h('div', { class: 'corpo' }, h('b', null, t.nome, t.inativo ? h('small', { class: 'selo aviso' }, 'inativo') : null), h('small', null, `${rotuloClasse(t.classe)} · ${t.em_uso} conta(s)`)),
      h('span', null, '›'))),
    h('button', { class: 'btn', onclick: () => editarTipo(null, recarregar) }, '+ Novo tipo'));
}

function editarTipo(t, recarregar) {
  folha(t ? 'Editar tipo' : 'Novo tipo', (corpo, fechar) => {
    const nome = h('input', { type: 'text', value: t ? t.nome : '', placeholder: 'Ex.: Ticket refeição' });
    const classe = h('select', { value: t ? t.classe : 'beneficio' }, CLASSES.map(([v, r]) => h('option', { value: v }, r)));
    classe.value = t ? t.classe : 'beneficio';
    corpo.append(campo('Nome', nome), campo('Comportamento', classe, t && t.em_uso ? 'Mudar o comportamento vale para as contas que usam este tipo.' : null),
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!nome.value.trim()) throw new Error('Informe o nome.');
        if (t) await PATCH(`/api/tipos-conta/${t.id}`, { nome: nome.value.trim(), classe: classe.value });
        else await POST('/api/tipos-conta', { nome: nome.value.trim(), classe: classe.value });
        fechar(); aviso('Salvo'); recarregar();
      }) }, 'Salvar'));
    if (t) corpo.append(h('div', { class: 'linha-botoes' },
      h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/tipos-conta/${t.id}`, { inativo: !t.inativo }); fechar(); recarregar(); }) }, t.inativo ? 'Reativar' : 'Inativar'),
      h('button', { class: 'btn link perigo', onclick: acao(async () => {
        if (!(await confirmar(`Excluir o tipo "${t.nome}"?`, 'Excluir', true))) return;
        await DEL(`/api/tipos-conta/${t.id}`); fechar(); aviso('Tipo excluído'); recarregar();
      }) }, 'Excluir')));
  });
}

async function detalheConta(c, recarregar) {
  const gestor = c.papel === 'dono' || c.papel === 'gestor';
  const dono = c.dono_id === estado.eu.id;
  folha(c.nome, async (corpo, fechar) => {
    corpo.append(h('p', { class: 'dica' }, `Saldo atual ${brl(c.saldo_atual)} · seu acesso: ${PAPEIS[c.papel] || c.papel}`));
    const acessos = h('div');
    corpo.append(h('h3', null, 'Quem tem acesso'), acessos);
    try {
      const ac = await GET(`/api/contas/${c.id}/acessos`);
      acessos.append(h('div', { class: 'linha item sem-clique' }, h('div', { class: 'corpo' }, h('b', null, c.dono_nome), h('small', null, 'dono')), null),
        ac.map(a => h('div', { class: 'linha item sem-clique' }, h('div', { class: 'corpo' }, h('b', null, a.nome), h('small', null, `${a.email} · ${PAPEIS[a.papel]}`)),
          (gestor || a.usuario_id === estado.eu.id) ? h('button', { class: 'btn link perigo', onclick: acao(async () => {
            if (!(await confirmar(a.usuario_id === estado.eu.id ? 'Sair desta conta compartilhada?' : `Remover o acesso de ${a.nome}?`, 'Remover', true))) return;
            await DEL(`/api/contas/${c.id}/acessos/${a.usuario_id}`); fechar(); recarregar();
          }) }, 'Remover') : null)));
    } catch (e) { acessos.append(h('p', { class: 'erro-form' }, e.message)); }
    if (gestor) {
      const email = h('input', { type: 'email', placeholder: 'email@exemplo.com' });
      const papel = h('select', { value: 'editor' }, ['leitor', 'editor', 'gestor'].map(p => h('option', { value: p }, PAPEIS[p])));
      corpo.append(h('h3', null, 'Compartilhar esta conta'), campo('E-mail', email), campo('Permissão', papel),
        h('button', { class: 'btn', onclick: acao(async () => {
          if (!email.value.includes('@')) throw new Error('E-mail inválido.');
          await POST(`/api/contas/${c.id}/convites`, { email: email.value.trim(), papel: papel.value });
          aviso('Convite enviado'); fechar();
        }) }, 'Enviar convite'),
        h('p', { class: 'dica' }, 'Cada pessoa continua vendo só as contas dela e as que você compartilhar. Contas privadas não aparecem para ninguém.'));
    }
    if (gestor && c.tipo === 'beneficio') {
      const rec = camposRecarga(c);
      const ativa = h('input', { type: 'checkbox', checked: c.recarga_valor_centavos ? !!c.recarga_ativa : true });
      corpo.append(h('h3', null, 'Recarga mensal'), ...rec.vista,
        h('label', { class: 'check' }, ativa, h('span', null, 'Recarga ativa')),
        h('button', { class: 'btn', onclick: acao(async () => {
          const rv = parseValor(rec.valor.value);
          if (Number.isNaN(rv) || rv <= 0 || !(+rec.dia.value >= 1 && +rec.dia.value <= 31)) throw new Error('Confira o valor e o dia da recarga.');
          await PUT_(`/api/contas/${c.id}/recarga`, { valor_centavos: rv, dia_mes: +rec.dia.value, ativa: ativa.checked });
          fechar(); aviso('Recarga atualizada'); await carregarCadastros(); recarregar();
        }) }, 'Salvar recarga'),
        h('p', { class: 'dica' }, 'Alterar o valor ou o dia atualiza as entradas previstas do mês em diante. O que já foi confirmado não muda; para um mês específico diferente, edite aquele lançamento. Desativar remove os previstos futuros.'));
    }
    if (dono && c.tipo === 'investimento') {
      let cfg = null;
      try { cfg = ((await GET('/api/investimentos')).investimentos.find(x => x.id === c.id && x.configurado)) || null; } catch { /* abre vazio */ }
      const campos = await camposInvestimento(cfg);
      corpo.append(h('h3', null, 'Investimento'), ...campos.vista,
        h('button', { class: 'btn', onclick: acao(async () => {
          await PUT_(`/api/contas/${c.id}/investimento`, campos.ler());
          fechar(); aviso('Investimento salvo'); await carregarCadastros(); recarregar();
        }) }, 'Salvar investimento'));
    }
    if (dono) {
      const nome = h('input', { type: 'text', value: c.nome });
      const tipos = (await GET('/api/tipos-conta')).filter(t => t.dono_id === estado.eu.id && (!t.inativo || t.id === c.tipo_conta_id));
      const tipo = h('select', null, tipos.map(t => h('option', { value: t.id }, t.nome)));
      tipo.value = c.tipo_conta_id || '';
      corpo.append(h('h3', null, 'Editar'), campo('Nome', nome), campo('Tipo', tipo),
        h('div', { class: 'linha-botoes' },
          h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/contas/${c.id}`, { nome: nome.value.trim() || c.nome, tipo_conta_id: tipo.value || null }); fechar(); await carregarCadastros(); recarregar(); }) }, 'Salvar'),
          h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/contas/${c.id}`, { inativa: !c.inativa }); fechar(); recarregar(); }) }, c.inativa ? 'Reativar' : 'Inativar')),
        h('button', { class: 'btn link perigo', onclick: acao(async () => {
          if (!(await confirmar(`Excluir a conta "${c.nome}" e TODOS os lançamentos dela? Não dá para desfazer.`, 'Excluir tudo', true))) return;
          await DEL(`/api/contas/${c.id}`); fechar(); aviso('Conta excluída'); recarregar();
        }) }, 'Excluir conta'));
    }
  });
}

// ---------- convites ----------
async function convites(raiz, ctx) {
  const c = await GET('/api/convites');
  const recarregar = () => convites(raiz, ctx);
  limpar(raiz).append(voltar('Convites'),
    h('h2', null, 'Recebidos'),
    c.recebidos.length ? c.recebidos.map(v => h('section', { class: 'cartao' },
      h('b', null, v.descricao), h('small', null, `${v.convidado_por_nome} convidou você${v.papel ? ' · ' + PAPEIS[v.papel] : ' · como portador (você verá só o que gastar)'}`),
      h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn sec', onclick: acao(async () => { await POST(`/api/convites/${v.id}/recusar`); recarregar(); }) }, 'Recusar'),
        h('button', { class: 'btn', onclick: acao(async () => { await POST(`/api/convites/${v.id}/aceitar`); aviso('Convite aceito'); await carregarCadastros(); recarregar(); }) }, 'Aceitar')))) : vazio('Nenhum convite pendente.'),
    h('h2', null, 'Enviados'),
    c.enviados.length ? c.enviados.map(v => h('div', { class: 'linha item sem-clique' }, h('div', { class: 'corpo' }, h('b', null, v.email), h('small', null, v.descricao)),
      h('button', { class: 'btn link perigo', onclick: acao(async () => { await POST(`/api/convites/${v.id}/cancelar`); recarregar(); }) }, 'Cancelar'))) : vazio('Nada aguardando resposta.'));
}

// ---------- categorias ----------
let abaCat = 'despesa';

async function categorias(raiz, ctx) {
  await carregarCadastros();
  const minhas = estado.categorias.filter(c => c.dono_id === estado.eu.id);
  const recarregar = () => categorias(raiz, ctx);
  const grupos = minhas.filter(c => c.tipo === abaCat && !c.pai_id);
  limpar(raiz).append(voltar('Categorias'),
    h('p', { class: 'dica' }, 'Estas são as suas categorias. Quem usa suas contas ou cartões lança nelas. Toque numa categoria para renomear, mover, mesclar, ocultar ou excluir.'),
    h('div', { class: 'segmentado' },
      ['despesa', 'receita'].map(t => h('button', { class: 'seg ' + (abaCat === t ? 'ativo' : ''), onclick: () => { abaCat = t; recarregar(); } }, t === 'despesa' ? 'Despesas' : 'Receitas'))),
    grupos.map(g => h('details', { class: 'cartao' },
      h('summary', null, h('b', { class: g.ativa ? '' : 'riscado' }, g.nome), h('small', null, `${minhas.filter(c => c.pai_id === g.id).length} subcategorias`)),
      minhas.filter(c => c.pai_id === g.id).map(f => h('button', { class: 'linha item', onclick: () => editarCategoria(f, minhas, recarregar) },
        h('div', { class: 'corpo' }, h('span', { class: f.ativa ? '' : 'riscado' }, f.nome), !f.ativa ? h('small', null, 'oculta') : null), h('span', null, '›'))),
      h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn link', onclick: () => novaCategoria(g, recarregar) }, '+ Subcategoria'),
        h('button', { class: 'btn link', onclick: () => editarGrupo(g, recarregar) }, 'Editar grupo')))),
    h('button', { class: 'btn sec', onclick: () => novoGrupo(abaCat, recarregar) }, '+ Novo grupo'));
}

function novoGrupo(tipo, recarregar) {
  folha('Novo grupo', (corpo, fechar) => {
    const nome = h('input', { type: 'text', maxlength: 80, placeholder: 'Ex.: Pets' });
    corpo.append(campo('Nome do grupo', nome), h('p', { class: 'dica' }, `Tipo: ${tipo === 'despesa' ? 'despesa' : 'receita'}.`),
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!nome.value.trim()) throw new Error('Informe o nome.');
        await POST('/api/categorias', { nome: nome.value.trim(), tipo });
        fechar(); recarregar();
      }) }, 'Criar grupo'));
  });
}

function novaCategoria(g, recarregar) {
  folha(`Nova subcategoria em ${g.nome}`, (corpo, fechar) => {
    const nome = h('input', { type: 'text', maxlength: 80 });
    corpo.append(campo('Nome', nome), h('button', { class: 'btn', onclick: acao(async () => {
      if (!nome.value.trim()) throw new Error('Informe o nome.');
      await POST('/api/categorias', { nome: nome.value.trim(), pai_id: g.id });
      fechar(); recarregar();
    }) }, 'Criar'));
  });
}

function editarGrupo(g, recarregar) {
  folha(`Grupo ${g.nome}`, (corpo, fechar) => {
    const nome = h('input', { type: 'text', value: g.nome, maxlength: 80 });
    corpo.append(campo('Nome', nome),
      h('button', { class: 'btn', onclick: acao(async () => { await PATCH(`/api/categorias/${g.id}`, { nome: nome.value.trim() }); fechar(); recarregar(); }) }, 'Salvar nome'),
      h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/categorias/${g.id}`, { ativa: !g.ativa }); fechar(); recarregar(); }) }, g.ativa ? 'Ocultar grupo' : 'Reativar grupo'),
      h('button', { class: 'btn link perigo', onclick: acao(async () => {
        if (!(await confirmar(`Excluir o grupo "${g.nome}"?`, 'Excluir', true))) return;
        try { await DEL(`/api/categorias/${g.id}`); fechar(); recarregar(); } catch (e) { aviso(e.message, true); }
      }) }, 'Excluir grupo'));
  });
}

function editarCategoria(c, minhas, recarregar) {
  folha(c.nome, (corpo, fechar) => {
    const nome = h('input', { type: 'text', value: c.nome, maxlength: 80 });
    const gruposMesmoTipo = minhas.filter(g => !g.pai_id && g.tipo === c.tipo);
    const grupo = h('select', { value: c.pai_id }, gruposMesmoTipo.map(g => h('option', { value: g.id }, g.nome)));
    const outras = minhas.filter(x => x.pai_id && x.tipo === c.tipo && x.id !== c.id);
    const destino = h('select', null, h('option', { value: '' }, 'Escolha a categoria de destino…'),
      gruposMesmoTipo.map(g => {
        const fs = outras.filter(x => x.pai_id === g.id);
        return fs.length ? h('optgroup', { label: g.nome }, fs.map(x => h('option', { value: x.id }, x.nome))) : null;
      }));
    corpo.append(campo('Nome', nome), campo('Grupo', grupo),
      h('button', { class: 'btn', onclick: acao(async () => {
        const b = { nome: nome.value.trim() };
        if (grupo.value !== c.pai_id) b.pai_id = grupo.value;
        await PATCH(`/api/categorias/${c.id}`, b); fechar(); recarregar();
      }) }, 'Salvar'),
      h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/categorias/${c.id}`, { ativa: !c.ativa }); fechar(); recarregar(); }) },
        c.ativa ? 'Ocultar (não aparece em novos lançamentos)' : 'Reativar'),
      h('h3', null, 'Mesclar em outra categoria'),
      h('p', { class: 'dica' }, 'Todos os lançamentos, recorrências, favorecidos e orçamentos desta categoria passam para a escolhida, e esta é excluída. Não dá para desfazer.'),
      campo('Destino', destino),
      h('button', { class: 'btn sec', onclick: acao(async () => {
        if (!destino.value) throw new Error('Escolha a categoria de destino.');
        const alvo = outras.find(x => x.id === destino.value);
        if (!(await confirmar(`Mesclar "${c.nome}" em "${alvo.nome}"?`, 'Mesclar', true))) return;
        const r = await POST(`/api/categorias/${c.id}/mesclar`, { destino_id: destino.value });
        fechar(); aviso(`Mesclada: ${r.lancamentos_movidos} lançamento(s) movido(s)`); recarregar();
      }) }, 'Mesclar e excluir esta'),
      h('button', { class: 'btn link perigo', onclick: acao(async () => {
        if (!(await confirmar(`Excluir a categoria "${c.nome}"?`, 'Excluir', true))) return;
        try { await DEL(`/api/categorias/${c.id}`); fechar(); recarregar(); } catch (e) { aviso(e.message, true); }
      }) }, 'Excluir categoria'));
  });
}

// ---------- recorrências ----------
async function recorrencias(raiz, ctx) {
  await carregarCadastros();
  const rs = await GET('/api/recorrencias');
  const recarregar = () => recorrencias(raiz, ctx);
  limpar(raiz).append(voltar('Recorrentes'),
    h('p', { class: 'dica' }, 'Contas fixas (aluguel, escola, assinaturas…). O app cria sozinho os previstos do mês atual e dos 5 seguintes: eles alimentam o "disponível de verdade".'),
    h('button', { class: 'btn', onclick: acao(async () => { const r = await POST('/api/recorrencias/gerar', { mes: mesISO(), ate: somarMes(mesISO(), 5) }); aviso(`${r.criadas} previsto(s) gerado(s)`); }) }, 'Gerar previstos agora'),
    rs.length ? rs.map(r => h('button', { class: 'linha item', onclick: () => editarRecorrencia(r, recarregar) },
      h('div', { class: 'corpo' }, h('b', null, r.favorecido_nome || r.descricao || 'Sem nome', r.ativa ? null : h('small', { class: 'selo aviso' }, 'pausada')),
        h('small', null, `dia ${r.dia_mes} · ${r.conta_nome || r.cartao_nome + ' ·· ' + r.plastico_final}${r.categoria_nome ? ' · ' + r.categoria_nome : ''}${r.fim ? ' · até ' + dataLonga(r.fim) : ''}`)),
      h('b', { class: r.tipo === 'receita' ? 'pos' : 'neg' }, brl(r.valor_centavos)))) : vazio('Nenhuma recorrência.'),
    h('button', { class: 'fab', 'aria-label': 'Nova recorrência', onclick: () => novaRecorrencia(recarregar) }, '+'));
}
// Altera a recorrência para os próximos meses: os previstos dela a partir do mês escolhido são refeitos; o confirmado não muda.
function editarRecorrencia(r, recarregar) {
  folha('Editar recorrência', (corpo, fechar) => {
    const d = destinos().find(x => (r.conta_id ? x.tipo === 'conta' && x.id === r.conta_id : x.tipo === 'plastico' && x.id === r.plastico_id));
    const dono = d ? d.dono : null;
    const valor = h('input', { type: 'text', inputmode: 'decimal', class: 'valor-grande', value: centavosParaCampo(r.valor_centavos) });
    const dia = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', value: r.dia_mes });
    const cat = h('select', null);
    const campoFav = campoFavorecido({ valor: r.favorecido_nome || '', dono: () => dono,
      aoEscolher: (x) => { if (x.categoria_padrao_id && [...cat.options].some(o => o.value === x.categoria_padrao_id)) cat.value = x.categoria_padrao_id; } });
    const forma = h('select', null, h('option', { value: '' }, '—'), Object.entries(FORMAS).map(([k, v]) => h('option', { value: k }, v)));
    forma.value = r.forma_pagamento || '';
    const fim = h('input', { type: 'date', value: r.fim ? String(r.fim).slice(0, 10) : '' });
    const quando = h('select', null, h('option', { value: mesISO() }, `Deste mês em diante (${nomeMes(mesISO())})`), h('option', { value: somarMes(mesISO(), 1) }, `Só a partir do próximo mês (${nomeMes(somarMes(mesISO(), 1))})`));
    limpar(cat).append(h('option', { value: '' }, 'Sem categoria'));
    const cs = estado.categorias.filter(c => c.dono_id === dono && c.ativa && c.tipo === r.tipo);
    for (const g of cs.filter(c => !c.pai_id)) {
      const fs = cs.filter(c => c.pai_id === g.id);
      if (fs.length) cat.append(h('optgroup', { label: g.nome }, fs.map(f => h('option', { value: f.id }, f.nome))));
    }
    cat.value = r.categoria_id || '';
    const puladosBox = h('div');
    const desenharPulados = async () => {
      let ms = [];
      try { ms = await GET(`/api/recorrencias/${r.id}/pulados`); } catch { /* sem a lista, segue sem ela */ }
      limpar(puladosBox);
      if (!ms.length) return;
      puladosBox.append(h('h3', null, 'Meses pulados'), h('small', { class: 'dica' }, 'Nestes meses esta recorrência não gera lançamento (você excluiu a ocorrência).'),
        ms.map(x => { const mes = String(x).slice(0, 7); return h('div', { class: 'linha item sem-clique' }, h('div', { class: 'corpo' }, h('b', null, nomeMes(mes))),
          h('button', { class: 'btn link', onclick: acao(async () => { await DEL(`/api/recorrencias/${r.id}/pulados/${mes}`); aviso(`${nomeMes(mes)} voltou a valer`); await desenharPulados(); recarregarLista(); }) }, 'Voltar a valer')); }));
    };
    const recarregarLista = () => recarregar();
    desenharPulados();
    const enviar = (extra, msg) => acao(async () => {
      const v = parseValor(valor.value);
      if (!(v > 0) || !(+dia.value >= 1 && +dia.value <= 31)) throw new Error('Informe um valor maior que zero e um dia entre 1 e 31.');
      const nome = campoFav.input.value.trim();
      const b = { valor_centavos: v, dia_mes: +dia.value, categoria_id: cat.value || undefined, favorecido_nome: nome || undefined, descricao: nome || undefined,
        forma_pagamento: r.conta_id ? (forma.value || undefined) : undefined, a_partir_de: quando.value, ...(fim.value ? { fim: fim.value } : { limpar_fim: true }), ...extra };
      const res = await PATCH(`/api/recorrencias/${r.id}`, b);
      fechar(); aviso(msg(res)); recarregar();
    });
    corpo.append(
      h('p', { class: 'dica' }, `${r.tipo === 'receita' ? 'Receita' : 'Despesa'} em ${r.conta_nome || r.cartao_nome + ' ·· ' + r.plastico_final}. Para trocar a conta ou o cartão, crie outra recorrência.`),
      campo('Valor (R$)', valor), campo('Dia do mês', dia), campo(r.tipo === 'receita' ? 'Pagador' : 'Favorecido', campoFav.el), campo('Categoria', cat),
      r.conta_id ? campo('Forma de pagamento', forma) : null,
      campo('Vale até (opcional)', fim, 'Deixe em branco para continuar todo mês.'),
      puladosBox,
      campo('Aplicar', quando, 'Os previstos desse período em diante (até 5 meses à frente) são refeitos com os dados novos. O que já foi confirmado não muda, e ajustes manuais feitos em previstos futuros são substituídos.'),
      h('button', { class: 'btn', onclick: enviar(r.ativa ? {} : { ativa: true }, () => 'Recorrência atualizada') }, r.ativa ? 'Salvar' : 'Salvar e reativar'),
      r.ativa ? h('button', { class: 'btn link', onclick: acao(async () => {
        if (!(await confirmar(`Pausar esta recorrência? Os previstos de ${nomeMes(quando.value)} em diante serão removidos e novos não serão gerados até você reativar.`, 'Pausar'))) return;
        const res = await PATCH(`/api/recorrencias/${r.id}`, { ativa: false, a_partir_de: quando.value });
        fechar(); aviso(`Recorrência pausada (${res.previstos_removidos} previsto(s) removido(s))`); recarregar(); }) }, 'Pausar recorrência') : null,
      h('button', { class: 'btn link perigo', onclick: () => excluirRecorrencia(r, () => { fechar(); recarregar(); }) }, 'Excluir'));
  });
}

// Exclusão da recorrência: o usuário escolhe se os previstos já criados saem junto ou ficam como lançamentos avulsos. O confirmado nunca é apagado.
function excluirRecorrencia(r, aoTerminar) {
  folha('Excluir recorrência', (corpo, fechar) => {
    const ir = (modo) => acao(async () => {
      const res = await DEL(`/api/recorrencias/${r.id}?previstos=${modo}`);
      fechar(); aviso(modo === 'remover' ? `Recorrência excluída (${res.previstos_removidos} previsto(s) removido(s))` : 'Recorrência excluída; os previstos ficaram como lançamentos avulsos'); aoTerminar();
    });
    corpo.append(h('p', null, 'O que fazer com os lançamentos previstos que esta recorrência já criou para os próximos meses? O que já foi confirmado não é apagado.'),
      h('div', { class: 'coluna-botoes' },
        h('button', { class: 'btn perigo', onclick: ir('remover') }, 'Excluir a recorrência e os previstos'),
        h('button', { class: 'btn sec', onclick: ir('manter') }, 'Excluir só a recorrência (manter os previstos)'),
        h('button', { class: 'btn sec', onclick: fechar }, 'Cancelar')));
  });
}

function novaRecorrencia(recarregar) {
  folha('Nova recorrência', (corpo, fechar) => {
    const dests = destinos();
    const tipo = h('select', null, h('option', { value: 'despesa' }, 'Despesa'), h('option', { value: 'receita' }, 'Receita'));
    const valor = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0,00' });
    const dia = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', placeholder: '10' });
    // primeira cobrança: se o dia deste mês já chegou, o mais comum é o lançamento já estar no saldo, então a sugestão é o próximo mês
    const primeira = h('select', null, h('option', { value: 'este' }, `Este mês (${nomeMes(mesISO())})`), h('option', { value: 'proximo' }, `Próximo mês (${nomeMes(somarMes(mesISO(), 1))})`));
    let mexeu = false;
    primeira.addEventListener('change', () => { mexeu = true; });
    dia.addEventListener('input', () => { if (!mexeu) primeira.value = +dia.value >= 1 && +dia.value <= new Date().getDate() ? 'proximo' : 'este'; });
    const campoFav = campoFavorecido({ placeholder: 'Ex.: Condomínio', dono: () => { const d = dests.find(x => x.valor === dest.value); return d ? d.dono : null; },
      aoEscolher: (r) => { if (r.categoria_padrao_id && !cat.value && [...cat.options].some(o => o.value === r.categoria_padrao_id)) cat.value = r.categoria_padrao_id; } });
    const fav = campoFav.input;
    const dest = h('select', null, dests.map(d => h('option', { value: d.valor }, d.rotulo)));
    const forma = h('select', null, h('option', { value: '' }, '—'), Object.entries(FORMAS).map(([k, v]) => h('option', { value: k }, v)));
    const cat = h('select', null);
    const montar = () => {
      const d = dests.find(x => x.valor === dest.value);
      limpar(cat).append(h('option', { value: '' }, 'Sem categoria'));
      if (!d) return;
      const cs = estado.categorias.filter(c => c.dono_id === d.dono && c.ativa && c.tipo === tipo.value);
      for (const g of cs.filter(c => !c.pai_id)) {
        const fs = cs.filter(c => c.pai_id === g.id);
        if (fs.length) cat.append(h('optgroup', { label: g.nome }, fs.map(f => h('option', { value: f.id }, f.nome))));
      }
    };
    const cFavRec = campo('Favorecido', campoFav.el);
    const rotuloFav = () => { cFavRec.firstChild.textContent = tipo.value === 'receita' ? 'Pagador' : 'Favorecido'; };
    dest.addEventListener('change', montar); tipo.addEventListener('change', () => { montar(); rotuloFav(); }); montar(); rotuloFav();
    corpo.append(campo('Tipo', tipo), campo('Valor (R$)', valor), campo('Dia do mês', dia), campo('Primeira cobrança', primeira, 'Se o dia deste mês já chegou e o valor já está no seu saldo, deixe "Próximo mês". Escolha "Este mês" para que ele apareça como pendente agora.'), cFavRec, campo('Conta ou cartão', dest), campo('Categoria', cat), campo('Forma de pagamento', forma),
      h('button', { class: 'btn', onclick: acao(async () => {
        const v = parseValor(valor.value), d = dests.find(x => x.valor === dest.value);
        if (!(v > 0) || !dia.value || !d) throw new Error('Informe valor, dia e conta/cartão.');
        const b = { tipo: tipo.value, valor_centavos: v, dia_mes: +dia.value, favorecido_nome: fav.value.trim() || null, categoria_id: cat.value || null,
          forma_pagamento: d.tipo === 'plastico' ? 'cartao' : (forma.value || null), descricao: fav.value.trim() || null };
        if (d.tipo === 'plastico') b.plastico_id = d.id; else b.conta_id = d.id;
        b.inicio = primeira.value === 'proximo' ? `${somarMes(mesISO(), 1)}-01` : `${mesISO()}-01`;
        await POST('/api/recorrencias', b);
        try { await POST('/api/recorrencias/gerar', { mes: mesISO() }); } catch { /* a geração automática do Início tenta de novo */ }
        fechar(); aviso('Recorrência criada'); recarregar();
      }) }, 'Criar'));
  });
}

// ---------- dispositivos e perfil ----------
async function dispositivos(raiz, ctx) {
  const ds = await GET('/api/dispositivos');
  const recarregar = () => dispositivos(raiz, ctx);
  limpar(raiz).append(voltar('Dispositivos'), h('p', { class: 'dica' }, 'Aparelhos com acesso à sua conta. Revogue os que você não usa mais ou perdeu.'),
    ds.map(d => h('div', { class: 'linha item sem-clique' },
      h('div', { class: 'corpo' }, h('b', null, d.nome, d.atual ? h('small', { class: 'selo' }, 'este aparelho') : null), h('small', null, `último uso ${dataLonga(d.ultimo_uso)}`)),
      d.atual ? null : h('button', { class: 'btn link perigo', onclick: acao(async () => { await DEL(`/api/dispositivos/${d.id}`); recarregar(); }) }, 'Revogar'))));
}

async function perfil(raiz, ctx) {
  const nome = h('input', { type: 'text', value: estado.eu.nome, maxlength: 80 });
  limpar(raiz).append(voltar('Meu perfil'), campo('Nome', nome), campo('E-mail', h('input', { type: 'text', value: estado.eu.email, disabled: true })),
    h('button', { class: 'btn', onclick: acao(async () => { estado.eu = await PATCH('/api/eu', { nome: nome.value.trim() }); aviso('Perfil atualizado'); }) }, 'Salvar'),
    h('h2', null, 'Seus dados'),
    h('a', { class: 'btn sec', href: '/api/exportar/completo', download: '' }, 'Exportar tudo (planilha + comprovantes)'),
    h('a', { class: 'btn link perigo', href: '#/mais/excluirConta' }, 'Excluir minha conta e todos os meus dados'));
}

// ---------- investimentos ----------
const IDX_ROTULO = { prefixado: 'Prefixado (% ao ano)', cdi: '% do CDI', selic: 'Selic + taxa', ipca: 'IPCA + taxa', poupanca: 'Poupança', manual: 'Valor informado por mim' };
const ROTULO_TAXA = { prefixado: 'Taxa (% ao ano)', cdi: 'Percentual do CDI (ex.: 100)', selic: 'Taxa acima da Selic (% ao ano; Tesouro Selic costuma ser 0)', ipca: 'Taxa acima do IPCA (% ao ano)' };
const pct = (n) => String(n).replace('.', ',');
const lerPct = (t) => { const v = parseFloat(String(t).trim().replace(',', '.')); return Number.isNaN(v) ? null : v; };
let subtiposCache = null;

// Campos de um investimento. `inv` = configuração atual (ou null). Devolve { vista, ler() } (ler lança erro se algo estiver incompleto).
async function camposInvestimento(inv) {
  subtiposCache = subtiposCache || await GET('/api/subtipos-investimento');
  const sub = h('select', null, subtiposCache.map(s => h('option', { value: s.chave }, s.rotulo)));
  sub.value = inv ? inv.subtipo : 'cdb';
  const idx = h('select', null, Object.entries(IDX_ROTULO).filter(([k]) => !['poupanca', 'manual'].includes(k)).map(([k, r]) => h('option', { value: k }, r)));
  idx.value = inv && !['poupanca', 'manual'].includes(inv.indexador) ? inv.indexador : 'cdi';
  const taxa = h('input', { type: 'text', inputmode: 'decimal', value: inv && inv.taxa != null ? pct(Number(inv.taxa)) : '', placeholder: 'Ex.: 100' });
  const aplic = h('input', { type: 'date', value: inv && inv.data_aplicacao ? String(inv.data_aplicacao).slice(0, 10) : '' });
  const aniv = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', value: inv && inv.dia_aniversario ? inv.dia_aniversario : '', placeholder: 'Ex.: 10' });
  const venc = h('input', { type: 'date', value: inv && inv.data_vencimento ? String(inv.data_vencimento).slice(0, 10) : '' });
  const isento = h('input', { type: 'checkbox', checked: inv ? !!inv.isento_ir : false });
  const alerta = h('input', { type: 'number', min: 0, max: 365, inputmode: 'numeric', value: inv ? inv.alerta_dias : 30 });
  const cIdx = campo('Como rende', idx), cTaxa = campo(ROTULO_TAXA.cdi, taxa), cAplic = campo('Data da aplicação', aplic), cAniv = campo('Dia de aniversário', aniv, 'Dia do mês em que o saldo é atualizado (o app cria o rendimento previsto nesse dia).');
  const cVenc = campo('Vencimento (opcional)', venc, 'Se informado, o app avisa na tela e por e-mail antes de vencer.');
  const cIsento = h('label', { class: 'check' }, isento, h('span', null, 'Isento de imposto de renda'));
  const cAlerta = campo('Avisar quantos dias antes do vencimento', alerta);
  const atual = () => subtiposCache.find(x => x.chave === sub.value);
  const redesenhar = (trocou) => {
    const s = atual();
    const manual = s.manual, poup = sub.value === 'poupanca';
    if (trocou) { idx.value = s.indexador === 'manual' || s.indexador === 'poupanca' ? 'cdi' : s.indexador; isento.checked = s.isento_ir; }
    cIdx.style.display = manual || poup ? 'none' : '';
    cTaxa.style.display = manual || poup ? 'none' : '';
    cAniv.style.display = manual ? 'none' : '';
    cAplic.style.display = manual ? 'none' : '';
    cIsento.style.display = manual ? 'none' : '';
    cTaxa.firstChild.textContent = ROTULO_TAXA[idx.value] || 'Taxa';
  };
  sub.addEventListener('change', () => redesenhar(true));
  idx.addEventListener('change', () => redesenhar(false));
  redesenhar(false);
  return {
    vista: [campo('Tipo de investimento', sub), cIdx, cTaxa, cAplic, cAniv, cVenc, cIsento, cAlerta,
      h('p', { class: 'dica' }, 'Tudo aqui é estimativa para ajudar no planejamento: confira com o extrato do banco e confirme o rendimento real quando ele cair. Não é recomendação de investimento.')],
    ler() {
      const s = atual();
      const b = { subtipo: sub.value, alerta_dias: Math.max(0, Math.min(365, +alerta.value || 0)), data_vencimento: venc.value || null };
      if (!s.manual) {
        const poup = sub.value === 'poupanca';
        if (!poup) {
          b.indexador = idx.value;
          b.taxa = lerPct(taxa.value);
          if (b.taxa === null) throw new Error('Informe a taxa do investimento.');
        }
        b.data_aplicacao = aplic.value || null;
        b.dia_aniversario = +aniv.value || (aplic.value ? +aplic.value.slice(8, 10) : null);
        if (!b.dia_aniversario) throw new Error('Informe o dia de aniversário (ou a data da aplicação).');
        b.isento_ir = isento.checked;
      }
      return b;
    },
  };
}

const SVGNS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs, ...filhos) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  for (const f of filhos) if (f != null) el.appendChild(f instanceof Node ? f : document.createTextNode(String(f)));
  return el;
}
const mesCurto = (ym) => { const [a, m] = ym.split('-'); return `${['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'][+m - 1]}/${a.slice(2)}`; };
const brlK = (c) => { const v = c / 100; return Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1).replace('.', ',')} mi` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)} mil` : String(Math.round(v)); };
const COR_CEN = { pessimista: 'var(--neg)', base: 'var(--marca)', otimista: 'var(--pos)' };
const ROT_CEN = { pessimista: 'Pessimista', base: 'Base', otimista: 'Otimista' };

// Gráfico de linhas: passado real (contínuo, cinza) + futuro estimado em 3 cenários (a base mais grossa).
function graficoEvolucao(p, mostrar) {
  const W = 340, H = 190, ML = 44, MR = 8, MT = 10, MB = 22;
  const meses = [...p.passado.map(x => x[0]), ...p.cenarios.base.map(x => x[0])];
  const idxFut = p.passado.length;                     // o ponto 0 do futuro (mês atual) é o mês seguinte ao passado
  const series = [];
  if (p.passado.length) series.push({ cor: 'var(--suave)', largura: 2, pts: p.passado.map((x, i) => [i, x[1]]) });
  for (const k of ['pessimista', 'base', 'otimista']) if (mostrar[k]) series.push({ cor: COR_CEN[k], largura: k === 'base' ? 2.5 : 1.5, tracejado: k !== 'base', pts: p.cenarios[k].map((x, i) => [idxFut + i, x[1]]) });
  const todos = series.flatMap(s => s.pts.map(q => q[1]));
  let lo = Math.min(...todos), hi = Math.max(...todos);
  if (hi === lo) { hi = lo + 100; }
  const folga = (hi - lo) * 0.08; lo = Math.max(0, lo - folga); hi += folga;
  const x = (i) => ML + (meses.length > 1 ? i * (W - ML - MR) / (meses.length - 1) : 0);
  const y = (v) => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo));
  const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': 'Evolução do patrimônio investido: passado e projeção' });
  for (let t = 0; t <= 3; t++) {
    const v = lo + (hi - lo) * t / 3;
    g.appendChild(svg('line', { x1: ML, x2: W - MR, y1: y(v), y2: y(v), stroke: 'var(--borda)', 'stroke-width': 1 }));
    g.appendChild(svg('text', { x: ML - 4, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 10, fill: 'var(--suave)' }, brlK(v * 1)));
  }
  [0, Math.floor((meses.length - 1) / 2), meses.length - 1].forEach((i, n) =>
    g.appendChild(svg('text', { x: x(i), y: H - 6, 'text-anchor': n === 0 ? 'start' : n === 2 ? 'end' : 'middle', 'font-size': 10, fill: 'var(--suave)' }, mesCurto(meses[i]))));
  if (p.passado.length) g.appendChild(svg('line', { x1: x(idxFut), x2: x(idxFut), y1: MT, y2: H - MB, stroke: 'var(--borda)', 'stroke-dasharray': '3 3' }));
  for (const s of series) {
    const d = s.pts.map(([i, v], n) => `${n ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
    g.appendChild(svg('path', { d, fill: 'none', stroke: s.cor, 'stroke-width': s.largura, 'stroke-linejoin': 'round', ...(s.tracejado ? { 'stroke-dasharray': '5 3' } : {}) }));
  }
  return g;
}

async function painelInvestimentos(horizonte, redesenhar) {
  const p = await GET(`/api/investimentos/painel?meses=${horizonte}&historico=12`);
  if (!p.contas.length || p.saldo_atual <= 0) return null;
  const mostrar = { pessimista: true, base: true, otimista: true };
  const area = h('div');
  const desenhar = () => {
    limpar(area).append(graficoEvolucao(p, mostrar));
  };
  desenhar();
  const chips = Object.keys(COR_CEN).map(k => h('button', { class: 'chip ativo', style: `border-color:${COR_CEN[k]}`, onclick: (e) => {
    mostrar[k] = !mostrar[k]; e.currentTarget.classList.toggle('ativo', mostrar[k]);
    if (!Object.values(mostrar).some(Boolean)) { mostrar[k] = true; e.currentTarget.classList.add('ativo'); }
    desenhar();
  } }, ROT_CEN[k]));
  const fim = (k) => p.cenarios[k][p.cenarios[k].length - 1][1];
  const hz = h('select', { onchange: (e) => redesenhar(+e.target.value) }, [12, 24, 60, 120].map(n => h('option', { value: n }, n >= 24 ? `${n / 12} anos` : '12 meses')));
  hz.value = String(horizonte);
  const maxAloc = Math.max(...p.alocacao.map(a => a.saldo), 1);
  return [
    h('section', { class: 'cartao' },
      h('div', { class: 'linha-controles' }, h('b', null, 'Patrimônio investido'), h('b', null, brl(p.saldo_atual))),
      h('div', { class: 'linha-controles' }, h('small', { class: 'bloco' }, 'Projeção até'), hz),
      area,
      h('div', { class: 'chips' }, chips),
      h('small', { class: 'bloco' }, 'Linha cinza: saldo real. Linhas coloridas: estimativa a partir das premissas (' + `base; pessimista e otimista deslocam Selic, CDI e IPCA em ${pct(p.deslocamento_pp)} ponto(s)).`),
      h('table', { class: 'tabela-mini' },
        h('tr', null, h('th', null, `Em ${horizonte >= 24 ? horizonte / 12 + ' anos' : '12 meses'}`), h('th', null, 'Bruto')),
        ['pessimista', 'base', 'otimista'].map(k => h('tr', null, h('td', null, ROT_CEN[k]), h('td', null, brl(fim(k))))),
        h('tr', null, h('td', null, 'Base, líquido de IR estimado'), h('td', null, brl(p.final_base_liquido))))),
    h('section', { class: 'cartao' },
      h('b', null, 'Alocação por tipo'),
      h('div', { class: 'barras' }, p.alocacao.map(a => h('div', { class: 'barra' }, h('span', null, a.rotulo),
        h('div', { class: 'trilho' }, h('div', { class: 'enchimento', style: `width:${Math.round(a.saldo / maxAloc * 100)}%` })), h('b', null, `${pct(a.percentual)}% · ${brl(a.saldo)}`))))),
    h('button', { class: 'btn sec', onclick: () => simuladorInvestimento(p) }, 'Simular aporte ou resgate'),
  ];
}

function simuladorInvestimento(p) {
  folha('Simulador', (corpo) => {
    const rendaveis = p.contas.filter(c => c.subtipo && !['renda_variavel', 'previdencia', 'outro'].includes(c.subtipo));
    const sel = h('select', null, rendaveis.map(c => h('option', { value: c.id }, c.nome)), h('option', { value: '' }, 'Outra taxa (informar)'));
    const taxa = h('input', { type: 'text', inputmode: 'decimal', value: '12', placeholder: 'Taxa bruta ao ano (%)' });
    const saldo = h('input', { type: 'text', inputmode: 'decimal', value: '0,00' });
    const inicial = h('input', { type: 'text', inputmode: 'decimal', value: '0,00' });
    const mensal = h('input', { type: 'text', inputmode: 'decimal', value: '0,00' });
    const resg = h('input', { type: 'text', inputmode: 'decimal', value: '0,00' });
    const mesResg = h('input', { type: 'number', min: 1, inputmode: 'numeric', placeholder: 'Ex.: 12' });
    const meses = h('input', { type: 'number', min: 1, max: 360, inputmode: 'numeric', value: 24 });
    const cen = h('select', null, h('option', { value: '0' }, 'Base'), h('option', { value: '-2' }, 'Pessimista (−2 p.p.)'), h('option', { value: '2' }, 'Otimista (+2 p.p.)'));
    const cTaxa = campo('Taxa bruta (% ao ano)', taxa), cSaldo = campo('Valor já investido (R$)', saldo);
    const mostra = () => { cTaxa.style.display = cSaldo.style.display = sel.value ? 'none' : ''; };
    sel.addEventListener('change', mostra); mostra();
    const res = h('div');
    const v = (el) => { const n = parseValor(el.value); if (Number.isNaN(n) || n < 0) throw new Error('Confira os valores em R$.'); return n; };
    corpo.append(
      h('p', { class: 'dica' }, 'Hipótese para planejamento: o aporte mensal entra no dia 1 de cada mês seguinte. Estimativa, não é recomendação.'),
      campo('Investimento', sel), cTaxa, cSaldo, campo('Aporte hoje (R$)', inicial), campo('Aporte por mês (R$)', mensal),
      campo('Resgate único (R$)', resg), campo('Resgate no mês número (opcional)', mesResg), campo('Prazo (meses)', meses), campo('Cenário', cen),
      h('button', { class: 'btn', onclick: acao(async () => {
        const corpoReq = { meses: Math.max(1, Math.min(360, +meses.value || 12)), delta_pp: +cen.value, aporte_inicial_centavos: v(inicial), aporte_mensal_centavos: v(mensal),
          resgate_centavos: v(resg), mes_resgate: +mesResg.value || null };
        if (sel.value) corpoReq.conta_id = sel.value;
        else { const t = lerPct(taxa.value); if (t === null) throw new Error('Informe a taxa.'); corpoReq.taxa_aa = t; corpoReq.saldo_inicial_centavos = v(saldo); }
        const r = await POST('/api/investimentos/simular', corpoReq);
        limpar(res).append(h('table', { class: 'tabela-mini' },
          h('tr', null, h('th', null, ''), h('th', null, 'Sem mudar nada'), h('th', null, 'Com a hipótese')),
          h('tr', null, h('td', null, 'Saldo bruto'), h('td', null, brl(r.base.final_bruto)), h('td', null, brl(r.hipotese.final_bruto))),
          h('tr', null, h('td', null, 'IR estimado'), h('td', null, brl(r.base.ir_estimado)), h('td', null, brl(r.hipotese.ir_estimado))),
          h('tr', null, h('td', null, 'Saldo líquido'), h('td', null, brl(r.base.final_liquido)), h('td', null, brl(r.hipotese.final_liquido)))),
          h('p', { class: 'dica' }, `Você colocaria ${brl(r.aportado_liquido)} a mais e ganharia ${brl(r.ganho_com_aportes)} de rendimento líquido estimado por causa disso.`));
      }) }, 'Simular'), res);
  });
}

async function investimentos(raiz, ctx) {
  await carregarCadastros();
  const r = await GET('/api/investimentos');
  const recarregar = () => investimentos(raiz, ctx);
  const hoje = hojeISO();
  let horizonte = +(sessionStorage.getItem('fin-inv-hz') || 24);
  const blocoPainel = h('div');
  const montarPainel = async (hz) => {
    horizonte = hz; try { sessionStorage.setItem('fin-inv-hz', String(hz)); } catch { /* sem storage: segue */ }
    try { const nos = await painelInvestimentos(hz, montarPainel); limpar(blocoPainel).append(nos); } catch { limpar(blocoPainel); }
  };
  montarPainel(horizonte);
  limpar(raiz).append(h('h1', null, 'Investimentos'),
    r.investimentos.length ? h('p', { class: 'dica' }, 'Estimativas para planejamento. O rendimento previsto aparece nos Próximos eventos; confirme com o valor real do extrato quando ele cair.') : null,
    blocoPainel,
    r.investimentos.length ? h('a', { class: 'linha item', href: '#/investimentos/premissas' }, h('div', { class: 'corpo' }, h('b', null, 'Premissas'),
      h('small', { class: 'bloco' }, `CDI ${pct(r.premissas.cdi)}% · Selic ${pct(r.premissas.selic)}% · IPCA ${pct(r.premissas.ipca)}% ao ano`)), h('span', null, '›')) : null,
    r.investimentos.length ? r.investimentos.map(i => {
      const conta = estado.contas.find(c => c.id === i.id);
      const dono = i.dono_id === estado.eu.id;
      const linhas = [];
      if (!i.configurado) linhas.push(h('small', { class: 'selo aviso' }, 'configure o investimento'));
      else if (i.manual) linhas.push(h('small', { class: 'bloco' }, `${i.rotulo} · valor informado por você`));
      else {
        linhas.push(h('small', { class: 'bloco' }, `${i.rotulo} · ${IDX_ROTULO[i.indexador]}${i.taxa != null && i.indexador !== 'poupanca' ? ' ' + pct(Number(i.taxa)) : ''}${i.isento_ir ? ' · isento de IR' : ` · IR ${pct(Math.round(i.aliquota_ir * 1000) / 10)}%`}`));
        if (i.rendimento_proximo) linhas.push(h('small', { class: 'bloco' }, `Próximo rendimento (${dataCurta(i.rendimento_proximo_data)}): ${brl(i.rendimento_proximo)} bruto${i.rendimento_proximo_liquido != null && !i.isento_ir ? ` · ${brl(i.rendimento_proximo_liquido)} líquido estimado` : ''}`));
      }
      if (i.data_vencimento) linhas.push(h('small', { class: 'bloco ' + (i.dias_para_vencimento != null && i.dias_para_vencimento <= i.alerta_dias ? 'neg' : '') },
        `Vence em ${dataLonga(i.data_vencimento)}${i.dias_para_vencimento != null ? (i.dias_para_vencimento < 0 ? ' (vencido)' : ` (${i.dias_para_vencimento} dia(s))`) : ''}`));
      return h('section', { class: 'cartao' },
        h('div', { class: 'linha-controles' }, h('b', null, i.nome), h('b', null, brl(i.saldo_atual))),
        ...linhas,
        dono ? h('div', { class: 'linha-botoes' },
          i.manual ? h('button', { class: 'btn sec', onclick: () => atualizarValor(i, recarregar) }, 'Atualizar valor') : null,
          h('button', { class: 'btn sec', onclick: () => conta && detalheConta(conta, recarregar) }, 'Configurar')) : null);
    }) : vazio('Nenhuma conta de investimento. Para criar uma, toque em ☰ › Contas e escolha o tipo Investimento.'));
}

function atualizarValor(i, recarregar) {
  folha(`Atualizar valor de ${i.nome}`, (corpo, fechar) => {
    const valor = h('input', { type: 'text', inputmode: 'decimal', class: 'valor-grande', value: centavosParaCampo(i.saldo_atual) });
    corpo.append(h('p', { class: 'dica' }, 'Informe quanto vale o investimento hoje. O app lança a diferença como ganho ou perda para o saldo ficar igual.'),
      campo('Valor atual (R$)', valor),
      h('button', { class: 'btn', onclick: acao(async () => {
        const v = parseValor(valor.value);
        if (Number.isNaN(v) || v < 0) throw new Error('Valor inválido.');
        const r = await POST(`/api/contas/${i.id}/atualizar-valor`, { valor_centavos: v });
        fechar(); aviso(r.diferenca_centavos ? `Valor atualizado (${brl(r.diferenca_centavos)})` : 'Sem diferença'); recarregar();
      }) }, 'Salvar'));
  });
}

export async function telaInvestimentos(raiz, ctx, sub) {
  return sub === 'premissas' ? premissas(raiz, ctx) : investimentos(raiz, ctx);
}

async function premissas(raiz, ctx) {
  const p = await GET('/api/premissas');
  const campoPct = (v) => h('input', { type: 'text', inputmode: 'decimal', value: pct(v) });
  const selic = campoPct(p.selic), cdi = campoPct(p.cdi), ipca = campoPct(p.ipca), tr = campoPct(p.tr);
  limpar(raiz).append(voltar('Premissas', '#/investimentos'),
    p.personalizadas ? null : h('p', { class: 'selo aviso' }, 'Valores iniciais de exemplo: ajuste para o que você espera'),
    h('p', { class: 'dica' }, 'Taxas anuais esperadas, usadas para estimar o rendimento dos próximos meses. Não são lidas de nenhum site: você as define e atualiza quando quiser. Ao salvar, os rendimentos previstos são recalculados.'),
    campo('Selic (% ao ano)', selic), campo('CDI (% ao ano)', cdi), campo('IPCA (% ao ano)', ipca), campo('TR (% ao ano)', tr, 'Usada só na poupança.'),
    h('button', { class: 'btn', onclick: acao(async () => {
      const b = { selic: lerPct(selic.value), cdi: lerPct(cdi.value), ipca: lerPct(ipca.value), tr: lerPct(tr.value) };
      if (Object.values(b).some(v => v === null)) throw new Error('Confira os valores.');
      await PUT_('/api/premissas', b); aviso('Premissas salvas'); premissas(raiz, ctx);
    }) }, 'Salvar'));
}

// ---------- administração (só quem é o ADMIN_EMAIL) ----------
async function administracao(raiz, ctx) {
  const us = await GET('/api/admin/usuarios');
  const quando = (iso) => iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : 'nunca';
  limpar(raiz).append(voltar('Administração'),
    h('p', { class: 'dica' }, `${us.length} pessoa(s) cadastrada(s). Contas e cartões são os ativos de que a pessoa é dona. O último acesso é aproximado (atualiza no máximo a cada hora).`),
    us.map(u => h('div', { class: 'linha item sem-clique' },
      h('div', { class: 'corpo' }, h('b', null, u.nome, u.id === estado.eu.id ? h('small', { class: 'selo' }, 'você') : null),
        h('small', null, u.email),
        h('small', null, `cadastro ${dataLonga(u.criado_em)} · último acesso ${quando(u.ultimo_acesso)}`)),
      h('small', { class: 'centro' }, `${u.contas} conta(s)`, h('br'), `${u.cartoes} cartão(ões)`))));
}

// ---------- sobre o aplicativo ----------
async function sobre(raiz, ctx) {
  let v = null;
  try { v = await api('GET', '/api/versao', undefined, { semSessao: true }); } catch { /* offline */ }
  const defasado = v && v.versao !== VERSAO_APP;
  limpar(raiz).append(voltar('Sobre o aplicativo'),
    h('section', { class: 'cartao' },
      h('p', null, h('b', null, 'Finanças'), ` · versão ${VERSAO_APP}`),
      v ? h('p', { class: 'dica' }, `Versão no servidor: ${v.versao}`) : h('p', { class: 'dica' }, 'Servidor indisponível no momento.'),
      defasado ? h('button', { class: 'btn', onclick: acao(async () => {
        const regs = await navigator.serviceWorker?.getRegistrations?.() || [];
        await Promise.all(regs.map(r => r.unregister()));
        for (const k of await caches.keys()) await caches.delete(k);
        location.reload();
      }) }, `Há uma versão nova (${v.versao}): atualizar agora`) : null),
    h('h2', null, 'Novidades'),
    (v ? v.historico : []).map(x => h('section', { class: 'cartao' },
      h('p', null, h('b', null, `Versão ${x.versao}`), x.data ? h('small', { class: 'dica' }, ` · ${dataLonga(x.data)}`) : null),
      h('ul', { class: 'novidades' }, x.itens.map(i => h('li', null, i))))));
}

// ---------- excluir conta ----------
async function excluirConta(raiz, ctx) {
  const r = await GET('/api/conta/exclusao');
  const lista = (rot, itens) => itens.length ? [h('b', null, rot), h('ul', { class: 'novidades' }, itens.map(i => h('li', null, i.nome + (i.outros.length ? ` — também perde o acesso: ${i.outros.join(', ')}` : ''))))] : [];
  const codigo = h('input', { type: 'text', inputmode: 'numeric', maxlength: 6, autocomplete: 'one-time-code', placeholder: '6 dígitos' });
  const conf = h('input', { type: 'text', placeholder: 'EXCLUIR', autocapitalize: 'characters' });
  const passo2 = h('div', { hidden: true },
    h('p', { class: 'dica' }, `Enviamos um código para ${estado.eu.email}. Informe-o e digite EXCLUIR.`),
    campo('Código recebido por e-mail', codigo), campo('Digite EXCLUIR para confirmar', conf),
    h('button', { class: 'btn perigo', onclick: acao(async () => {
      await api('DELETE', '/api/conta', { confirmacao: conf.value, codigo: codigo.value });
      aviso('Conta e dados excluídos');
      window.dispatchEvent(new Event('sessao-expirada'));
    }) }, 'Excluir tudo agora, sem volta'));
  limpar(raiz).append(voltar('Excluir minha conta'),
    h('section', { class: 'cartao' },
      h('p', null, 'Isto apaga ', h('b', null, 'imediatamente e de forma definitiva'), ' o seu acesso e os dados que são seus:'),
      ...lista('Contas (com todos os lançamentos)', r.contas), ...lista('Cartões de crédito (com faturas e lançamentos)', r.cartoes),
      h('p', { class: 'dica' }, `${r.lancamentos} lançamento(s) nessas contas e cartões, além de suas categorias, favorecidos, orçamento, recorrências, comprovantes e dispositivos.`),
      r.compartilhadas.length ? h('p', { class: 'aviso-forte' }, 'Atenção: o que você divide com outras pessoas será apagado também para elas. Elas deixarão de ver o histórico dessas contas e cartões.') : null,
      h('p', { class: 'dica' }, 'O que você lançou em contas de outras pessoas continua com elas, sem o seu nome (aparece como "Ex-usuário").')),
    h('a', { class: 'btn sec', href: '/api/exportar/completo', download: '' }, 'Antes, exportar tudo (planilha + comprovantes)'),
    h('button', { class: 'btn perigo', onclick: acao(async () => { await POST('/api/conta/exclusao/codigo'); passo2.hidden = false; aviso('Código enviado por e-mail'); }) }, 'Quero excluir: enviar código por e-mail'),
    passo2);
}
