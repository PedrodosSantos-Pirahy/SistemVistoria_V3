import { Component, signal, computed, inject, OnInit, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer } from '@angular/platform-browser';

// Interface para ocupação (Agora com ID!)
interface IntervaloOcupado {
  inicio: string;
  fim: string;
  id: string; // 🔥 Novo campo para saber quem é quem
}

@Component({
  selector: 'app-monitoramento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './monitoramento.component.html'
})
export class MonitoramentoComponent implements OnInit {
  
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

  pdfUrlSegura = computed(() => {
    const item = this.itemSelecionado();
    if (!item || !item.tem_pdf) return null;
    return this.sanitizer.bypassSecurityTrustResourceUrl(`http://192.168.53.193:5002/pdf/${item.id}`);
  });

  // --- EDIÇÃO (Lógica do Agendamento) ---
  modalEdicaoAberto = signal(false);
  
  // Ocupações do dia selecionado no modal
  ocupacoesDoDia = signal<IntervaloOcupado[]>([]);

  formEdicao = signal({ 
    id: '', 
    placa: '', 
    data: '', // YYYY-MM-DD
    hora: '', // HH:MM
    duracao: 30,
    local: '', 
    pre_ordens: ['', '', '', '', ''] 
  });

  // Efeito para carregar ocupações quando a DATA da edição muda
  constructor() {
    effect(() => {
        const data = this.formEdicao().data;
        if (this.modalEdicaoAberto() && data) {
            this.carregarOcupacoes(data);
        }
    });
  }

  ngOnInit() {
    this.carregarDados();
    setInterval(() => this.carregarDados(), 45000);
  }

  carregarDados() {
    const page = this.paginaAtual();
    const limit = this.itensPorPagina();
    const busca = this.filtroGeral();
    if (!busca) this.loading.set(true);

    this.http.get<any>(`http://192.168.53.193:5002/monitoramento?page=${page}&limit=${limit}&q=${busca}`)
      .subscribe({
        next: (res) => {
          this.dadosTabela.set(res.data);
          if (res.meta) {
            this.totalItens.set(res.meta.total_items);
            this.totalPaginas.set(res.meta.total_pages);
          }
          this.loading.set(false);
        },
        error: (err) => { this.loading.set(false); }
      });
  }

  // --- ABERTURA DO MODAL DE EDIÇÃO ---
  // Em monitoramento.component.ts

  abrirEdicao(event: Event, item: any) {
    event.stopPropagation();
    
    // Formata a data para YYYY-MM-DD
    const [dia, mes, ano] = item.data.split('/');
    const dataIso = `${ano}-${mes}-${dia}`;

    // 🔥 AGORA VAI PUXAR TUDO AUTOMATICAMENTE
    const ordensArray = [
        item.pre_ordem1 || '', 
        item.pre_ordem2 || '', 
        item.pre_ordem3 || '',
        item.pre_ordem4 || '', 
        item.pre_ordem5 || ''
    ];

    this.formEdicao.set({ 
        id: item.id, 
        placa: item.placa,
        data: dataIso,
        hora: item.h_inicio,
        duracao: item.duracao || 30, // Pega a duração do banco ou 30 padrão
        local: item.local || 'Matriz',
        pre_ordens: ordensArray
    });

    this.modalEdicaoAberto.set(true);
  }

  // --- LÓGICA VISUAL DE SLOTS (Igual ao Agendamento) ---
  carregarOcupacoes(data: string) {
    this.http.get<IntervaloOcupado[]>(`http://192.168.53.193:5002/agendamentos-dia?data=${data}`)
      .subscribe(dados => this.ocupacoesDoDia.set(dados));
  }

  private timeToMinutes(time: string): number {
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  }

  // 🔥 COMPUTED PODEROSA: Gera a grade visual ignorando o próprio ID
  slotsVisuais = computed(() => {
    const times = [];
    const ocupacoes = this.ocupacoesDoDia();
    const meuId = this.formEdicao().id; // ID de quem estou editando
    
    const now = new Date();
    const isToday = this.formEdicao().data === now.toISOString().split('T')[0];
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();

    for (let h = 8; h <= 17; h++) {
      for (let m of ['00', '15', '30', '45']) {
        const slotTimeStr = `${h.toString().padStart(2, '0')}:${m}`;
        const slotMin = this.timeToMinutes(slotTimeStr);

        // 1. Passado?
        let isPast = false;
        if (isToday) {
           if (h < currentHour || (h === currentHour && Number(m) < currentMinute)) {
             isPast = true;
           }
        }

        // 2. Calcula Lotação (IGNORANDO O PRÓPRIO ID)
        let load = 0;
        for (const ocupacao of ocupacoes) {
           // 🚨 O PULO DO GATO: Se a ocupação for do item que estou editando, IGNORA.
           // Assim o usuário vê o slot dele como "livre" (verde) para poder manter ou trocar.
           if (ocupacao.id === meuId) continue;

           const inicioMin = this.timeToMinutes(ocupacao.inicio);
           const fimMin = this.timeToMinutes(ocupacao.fim);

           if (slotMin >= inicioMin && slotMin < fimMin) {
             load++;
           }
        }

        times.push({ 
          time: slotTimeStr, 
          load: load, 
          isPast: isPast 
        });
      }
    }
    return times;
  });

  selecionarHorario(time: string) {
    this.formEdicao.update(v => ({ ...v, hora: time }));
  }
  // Adicione este método na sua classe
  aoMudarDataEdicao(novaData: string) {
    this.formEdicao.update(atual => ({
      ...atual,        // Mantém placa, id, etc.
      data: novaData,  // Atualiza a data
      hora: ''         // Limpa a hora para forçar o usuário a escolher de novo
    }));
    
    // O effect() que já existe no seu constructor vai perceber essa mudança 
    // e chamar o carregarOcupacoes() automaticamente.
  }

  salvarEdicao() {
    this.http.post(`http://192.168.53.193:5000/gerenciar-agendamento`, this.formEdicao())
      .subscribe({
        next: () => {
          this.modalEdicaoAberto.set(false);
          this.carregarDados();
          alert('✅ Agendamento atualizado!');
        },
        error: (err) => alert(err.error?.error || 'Erro ao atualizar')
      });
  }

  desmarcarAgendamento() {
    if (confirm('Deseja realmente desmarcar este agendamento?')) {
        const payload = { id: this.formEdicao().id, acao: 'cancelar', motivo: 'Desmarcado pelo Monitoramento' };
        this.http.post(`http://192.168.53.193:5000/gerenciar-agendamento`, payload).subscribe(() => {
            this.modalEdicaoAberto.set(false);
            this.carregarDados();
        });
    }
  }

  // Métodos auxiliares
  aoPesquisar() { this.paginaAtual.set(1); this.carregarDados(); }
  mudarPagina(p: number) { if (p >= 1 && p <= this.totalPaginas()) { this.paginaAtual.set(p); this.carregarDados(); } }
  abrirDetalhes(item: any) { this.itemSelecionado.set(item); this.paginaDetalhesAberta.set(true); this.carregarDetalhes(item.id); }
  fecharDetalhes() { this.paginaDetalhesAberta.set(false); }
  carregarDetalhes(id: string) {
      if(!id) return;
      this.loadingDetalhes.set(true);
      this.http.get<any>(`http://192.168.53.193:5002/detalhes/${id}`).subscribe({
        next: (res) => {
            if(res.encontrado) { this.detalhesChecklist.set(res); this.fotosDisponiveis.set(res.fotos); }
            this.loadingDetalhes.set(false);
        },
        error: () => this.loadingDetalhes.set(false)
      });
  }
  getFotoUrl(tipo: string): string { return `http://192.168.53.193:5002/foto/${this.itemSelecionado()?.id}/${tipo}`; }
}