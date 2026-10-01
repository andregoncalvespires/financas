import { h, GET, POST, PATCH, PUT_, DEL, brl, folha, aviso, acao, campo, limpar, vazio, parseValor, centavosParaCampo, hojeISO, mesISO, dataLonga, PAPEIS, FORMAS, confirmar, api } from './util.js';
import { estado, carregarCadastros, destinos } from './form.js';
import { VERSAO_APP } from './versao.js';

const voltar = h_voltar;
function h_voltar(titulo) {
  return h('div', { class: 'topo-sub' }, h('a', { href: '#/mais', class: 'icone', 'aria-label': 'Voltar' }, '‹'), h('h1', null, titulo));
}

export async function mais(raiz, ctx, sub) {
  const telas = { contas, tiposConta, convites, categorias, recorrencias, dispositivos, perfil, sobre, excluirConta };
  if (sub && telas[sub]) return telas[sub](raiz, ctx);
  let n = 0;
  try { const c = await GET('/api/convites'); n = c.recebidos.length; } catch { /* ignora */ }
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
  ['poupanca', 'Poupança (reserva)'], ['investimento', 'Investimento (reserva)'], ['beneficio', 'Benefício: ticket/vale (saldo à parte)']];

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
    const atualizarRec = () => { const t = tipos.find(x => x.id === tipo.value); blocoRec.style.display = (t && t.classe === 'beneficio') ? '' : 'none'; };
    tipo.addEventListener('change', atualizarRec); atualizarRec();
    corpo.append(campo('Nome', nome), campo('Tipo', tipo, 'Crie outros tipos em Mais › Tipos de conta.'), campo('Saldo inicial (R$)', saldo, 'Saldo real na data abaixo; os lançamentos somam a partir dela.'), campo('Data do saldo inicial', data), blocoRec,
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
        await POST('/api/contas', b);
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
    h('p', { class: 'dica' }, 'Contas fixas (aluguel, escola, assinaturas…). Gere os previstos do mês: eles alimentam o "disponível de verdade".'),
    h('button', { class: 'btn', onclick: acao(async () => { const r = await POST('/api/recorrencias/gerar', { mes: mesISO() }); aviso(`${r.criadas} previsto(s) gerado(s) para este mês`); }) }, 'Gerar previstos deste mês'),
    rs.length ? rs.map(r => h('div', { class: 'linha item sem-clique' },
      h('div', { class: 'corpo' }, h('b', null, r.favorecido_nome || r.descricao || 'Sem nome'), h('small', null, `dia ${r.dia_mes} · ${r.conta_nome || r.cartao_nome + ' ·· ' + r.plastico_final}${r.categoria_nome ? ' · ' + r.categoria_nome : ''}`)),
      h('div', null, h('b', { class: r.tipo === 'receita' ? 'pos' : 'neg' }, brl(r.valor_centavos)),
        h('button', { class: 'btn link perigo', onclick: acao(async () => { if (await confirmar('Excluir esta recorrência? Os previstos já gerados permanecem.', 'Excluir', true)) { await DEL(`/api/recorrencias/${r.id}`); recarregar(); } }) }, 'Excluir')))) : vazio('Nenhuma recorrência.'),
    h('button', { class: 'btn sec', onclick: () => novaRecorrencia(recarregar) }, '+ Nova recorrência'));
}
function novaRecorrencia(recarregar) {
  folha('Nova recorrência', (corpo, fechar) => {
    const dests = destinos();
    const tipo = h('select', null, h('option', { value: 'despesa' }, 'Despesa'), h('option', { value: 'receita' }, 'Receita'));
    const valor = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0,00' });
    const dia = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', placeholder: '10' });
    const fav = h('input', { type: 'text', placeholder: 'Ex.: Condomínio' });
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
    dest.addEventListener('change', montar); tipo.addEventListener('change', montar); montar();
    corpo.append(campo('Tipo', tipo), campo('Valor (R$)', valor), campo('Dia do mês', dia), campo('Favorecido', fav), campo('Conta ou cartão', dest), campo('Categoria', cat), campo('Forma de pagamento', forma),
      h('button', { class: 'btn', onclick: acao(async () => {
        const v = parseValor(valor.value), d = dests.find(x => x.valor === dest.value);
        if (!(v > 0) || !dia.value || !d) throw new Error('Informe valor, dia e conta/cartão.');
        const b = { tipo: tipo.value, valor_centavos: v, dia_mes: +dia.value, favorecido_nome: fav.value.trim() || null, categoria_id: cat.value || null,
          forma_pagamento: d.tipo === 'plastico' ? 'cartao' : (forma.value || null), descricao: fav.value.trim() || null };
        if (d.tipo === 'plastico') b.plastico_id = d.id; else b.conta_id = d.id;
        await POST('/api/recorrencias', b);
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
