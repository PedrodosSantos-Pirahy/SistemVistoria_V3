import { Component, signal, computed, inject, OnInit, effect } from '@angular/core';
import { ApiService } from '../../services/app.service'; // Importe o serviço
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer } from '@angular/platform-browser';

interface IntervaloOcupado {
  inicio: string;
  fim: string;
  id: string;
}

@Component({
  selector: 'app-monitoramento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './monitoramento.component.html'
})
export class MonitoramentoComponent implements OnInit {
  
  private apiService: ApiService = inject(ApiService);
  private http: HttpClient = inject(HttpClient);
  private sanitizer: DomSanitizer = inject(DomSanitizer);

  // --- PAGINAÇÃO & DADOS ---
  paginaAtual = signal(1);
  itensPorPagina = signal(20);
  totalItens = signal(0);
  totalPaginas = signal(1);
  dadosTabela = signal<any[]>([]); 
  filtroGeral = signal('');
  loading = signal(true); 
  
  // --- DETALHES & PDF ---
  paginaDetalhesAberta = signal(false);
  itemSelecionado = signal<any>(null);
  detalhesChecklist = signal<any>(null);
  fotosDisponiveis = signal<any>(null);
  loadingDetalhes = signal(false);
  
  // 🔥 DECLARAÇÃO DO TIMESTAMP (Obrigatório)
  timestampFotos = signal(0);

  // --- NOVOS ESTADOS PARA CANCELAMENTO ---
  showCancelModal = signal(false);
  motivoCancelamento = signal('');
  usuarioNomeLogado = ''; // Variável simples para o nome fixo

pdfUrlSegura = computed(() => {
    const item = this.itemSelecionado();
    if (!item || !item.tem_pdf) return null;
    // Usa o helper do serviço para montar a URL correta
    const url = this.apiService.getPdfUrl(item.id);
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  });

  // --- EDIÇÃO ---
  modalEdicaoAberto = signal(false);
  ocupacoesDoDia = signal<IntervaloOcupado[]>([]);

  formEdicao = signal({ 
    id: '', placa: '', data: '', hora: '', 
    duracao: 30, local: '', pre_ordens: ['', '', '', '', ''] 
  });

constructor() {
  effect(() => {
    const data = this.formEdicao().data;
    const local = this.formEdicao().local; // 🔥 NOVO: Agora vigia também a Unidade
    
    // Se o modal estiver aberto e tivermos data e local, busca a ocupação correta
    if (this.modalEdicaoAberto() && data && local) {
        this.carregarOcupacoes(data, local);
    }
  });
}
readonly tipoLocal = signal<'Qualquer' | 'Matriz' | 'Filial'>('Qualquer');
readonly tipoStatus = signal<'Todas' | 'Pendentes' | 'Realizadas'>('Todas');
ngOnInit() {
    // 2. Configura o filtro baseado no usuário logado
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
        const user = JSON.parse(dados);
        this.usuarioNomeLogado = user.nome;
        if (user.local && (user.local === 'Matriz' || user.local === 'Filial')) {
            this.tipoLocal.set(user.local);
        }
    }
    this.carregarDados();
    setInterval(() => this.carregarDados(), 45000);
}
carregarDados() {
    const page = this.paginaAtual();
    const limit = this.itensPorPagina();
    const busca = this.filtroGeral();
    const local = this.tipoLocal(); // 👈 Pega o valor do sinal
    const status = this.tipoStatus();

    if (!busca) this.loading.set(true);

    this.apiService.getMonitoramento(page, limit, busca, local, status).subscribe({
        next: (res) => {
            this.dadosTabela.set(res.data);
            if (res.meta) {
                this.totalItens.set(res.meta.total_items);
                this.totalPaginas.set(res.meta.total_pages);
            }
            this.loading.set(false);
        },
        error: () => this.loading.set(false)
    });
}
// No arquivo: monitoramento.component.ts

// Função genérica para atualizar campos simples (placa, duração, etc)
updateEdicao(campo: string, valor: any) {
  this.formEdicao.update(atual => ({ ...atual, [campo]: valor }));
}

// Função específica para trocar o local (limpa a hora para forçar nova escolha)
setLocalEdicao(local: string) {
  this.formEdicao.update(atual => ({ ...atual, local: local, hora: '' }));
}

// Função para atualizar uma ordem específica dentro do array
updatePreOrdemEdicao(index: number, valor: string) {
  this.formEdicao.update(atual => {
    const novas = [...atual.pre_ordens];
    novas[index] = valor;
    return { ...atual, pre_ordens: novas };
  });
}
  // --- AÇÕES PRINCIPAIS ---

setStatus(status: 'Todas' | 'Pendentes' | 'Realizadas') {
    this.tipoStatus.set(status);
    this.paginaAtual.set(1);
    this.carregarDados();
}

  setLocal(local: 'Qualquer' | 'Matriz' | 'Filial') {
    this.tipoLocal.set(local);
    this.paginaAtual.set(1); // Volta para a página 1 ao filtrar
    this.carregarDados();
}
  // 🔥 1. ABRIR DETALHES (CORRIGIDO PARA FOTOS)
  abrirDetalhes(item: any) { 
      // Primeiro: Gera um número novo para enganar o cache
      this.timestampFotos.set(new Date().getTime());
      
      // Segundo: Seleciona o item e abre a tela
      this.itemSelecionado.set(item); 
      this.paginaDetalhesAberta.set(true); 
      
      // Terceiro: Busca os dados
      this.carregarDetalhes(item.id); 
  }
  
  fecharDetalhes() { 
      this.paginaDetalhesAberta.set(false); 
  }
  
carregarDetalhes(id: string) {
      if(!id) return;
      this.loadingDetalhes.set(true);
      // Substituído: Chamada via ApiService
      this.apiService.getDetalhesFinalizados(id).subscribe({
        next: (res) => {
            if(res.encontrado) { 
                this.detalhesChecklist.set(res);
                this.fotosDisponiveis.set(res.fotos);
            }
            this.loadingDetalhes.set(false);
        },
        error: () => this.loadingDetalhes.set(false)
      });
  }

  // 🔥 2. GERADOR DE URL (Fica igual, mas agora recebe o timestamp certo)
getFotoUrl(tipo: string): string { 
      // Substituído: Usa o helper do serviço
      return this.apiService.getFotoUrl(this.itemSelecionado()?.id, tipo); 
  }

  // --- EDIÇÃO ---
  aoMudarDataEdicao(novaData: string) {
    this.formEdicao.update(atual => ({ ...atual, data: novaData, hora: '' }));
  }

  abrirEdicao(event: Event, item: any) {
    event.stopPropagation();
    const [dia, mes, ano] = item.data.split('/');
    const dataIso = `${ano}-${mes}-${dia}`;
    const ordensArray = [ item.pre_ordem1 || '', item.pre_ordem2 || '', item.pre_ordem3 || '', item.pre_ordem4 || '', item.pre_ordem5 || '' ];

    this.formEdicao.set({ 
        id: item.id, placa: item.placa, data: dataIso, hora: item.h_inicio,
        duracao: item.duracao || 30, local: item.local || 'Matriz', pre_ordens: ordensArray
    });
    this.modalEdicaoAberto.set(true);
  }

// No monitoramento.component.ts
carregarOcupacoes(data: string, local: string) {
    this.apiService.getAgendamentosDia(data, local).subscribe(dados => {
        this.ocupacoesDoDia.set(dados);
    });
}
  private timeToMinutes(time: string): number {
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  }

  slotsVisuais = computed(() => {
    const times = [];
    const ocupacoes = this.ocupacoesDoDia();
    const meuId = this.formEdicao().id; 
    const now = new Date();
    const isToday = this.formEdicao().data === now.toISOString().split('T')[0];
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();

    for (let h = 8; h <= 17; h++) {
      for (let m of ['00', '15', '30', '45']) {
        const slotTimeStr = `${h.toString().padStart(2, '0')}:${m}`;
        const slotMin = this.timeToMinutes(slotTimeStr);
        let isPast = false;
        if (isToday) { if (h < currentHour || (h === currentHour && Number(m) < currentMinute)) isPast = true; }

        let load = 0;
        for (const ocupacao of ocupacoes) {
           if (ocupacao.id === meuId) continue;
           const inicioMin = this.timeToMinutes(ocupacao.inicio);
           const fimMin = this.timeToMinutes(ocupacao.fim);
           if (slotMin >= inicioMin && slotMin < fimMin) load++;
        }
        times.push({ time: slotTimeStr, load: load, isPast: isPast });
      }
    }
    return times;
  });

  selecionarHorario(time: string) { this.formEdicao.update(v => ({ ...v, hora: time })); }

salvarEdicao() {
    // Substituído: Chamada via ApiService (Porta 5000 no Dev / /api em Prod)
    this.apiService.gerenciarAgendamento(this.formEdicao()).subscribe({
        next: () => {
          this.modalEdicaoAberto.set(false);
          this.carregarDados();
          alert('✅ Agendamento atualizado!');
        },
        error: (err) => alert(err.error?.error || 'Erro ao atualizar')
    });
  }

desmarcarAgendamento() {
    // Apenas abre o novo modal de cancelamento
    this.showCancelModal.set(true);
  }

  fecharModalCancelamento() {
    this.showCancelModal.set(false);
    this.motivoCancelamento.set('');
  }

  confirmarCancelamentoMonitoramento() {
    const idAgendamento = this.formEdicao().id;
    const motivo = this.motivoCancelamento();

    if (!motivo) {
      alert('Por favor, informe o motivo do cancelamento.');
      return;
    }

    const payload = {
      id: idAgendamento,
      nome: this.usuarioNomeLogado, // Nome vindo do login, sem alteração
      motivo: motivo
    };

    // Usa o endpoint /cancelar que já registra nome e motivo no banco
    this.apiService.cancelarVistoria(payload).then(async (res) => {
      if (res.ok) {
        alert('✅ Agendamento cancelado com sucesso!');
        this.fecharModalCancelamento();
        this.modalEdicaoAberto.set(false); // Fecha também o modal de edição
        this.carregarDados();
      } else {
        alert('Erro ao cancelar agendamento.');
      }
    }).catch(() => alert('Erro de conexão com o servidor.'));
  }

  aoPesquisar() { this.paginaAtual.set(1); this.carregarDados(); }
  mudarPagina(p: number) { if (p >= 1 && p <= this.totalPaginas()) { this.paginaAtual.set(p); this.carregarDados(); } }
}