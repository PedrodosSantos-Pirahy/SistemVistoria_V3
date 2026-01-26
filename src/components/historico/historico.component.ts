import {
  Component,
  ChangeDetectionStrategy,
  signal,
  computed,
  OnInit,
  inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';

/* =======================
   Interface
======================= */
interface Historico {
  id: string;
  placa: string;
  data: string;
  hora: string;
  pre_Ordem: string;
  transportadora: string;
  status: 'Concluida' | 'Cancelada';
  liberacao: string;
  vistoriador: string;
  pdf: string;
}

/* =======================
   Component
======================= */
@Component({
  selector: 'app-historico',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historico.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class HistoricoComponent implements OnInit {

  private http = inject(HttpClient);
  private router = inject(Router);

  /* =======================
     State
  ======================= */
  historico = signal<Historico[]>([]);
  buscaPlaca = signal('');
  buscaTransp = signal('');
  ordemSelecionada = signal<'asc' | 'desc'>('desc');

  carregando = signal(false);
  erro = signal<string | null>(null);

  /* =======================
     Lifecycle
  ======================= */
  ngOnInit(): void {
    this.buscarHistorico();
  }

  /* =======================
     HTTP
  ======================= */
  private buscarHistorico(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<any>('http://192.168.2.100:5002/historico')
      .subscribe({
        next: res => {
          const dados: Historico[] = (res?.historico ?? [])
            .map((h: any) => {
              const statusNormalizado = (h.vr ?? '')
                .toString()
                .trim()
                .toLowerCase();

              let statusFinal: 'Concluida' | 'Cancelada' | null = null;

              if (statusNormalizado === 'concluida' || statusNormalizado === 'concluído') {
                statusFinal = 'Concluida';
              }

              if (statusNormalizado === 'cancelada' || statusNormalizado === 'cancelado') {
                statusFinal = 'Cancelada';
              }

              // 🚫 ignora qualquer outro status
              if (!statusFinal) return null;

              return {
                id: `${h.Placa}-${h.Data}-${h['Hora Inicio']}`,
                placa: (h.Placa ?? '').toUpperCase(),
                data: h.Data ?? '',
                hora: h['Hora Inicio'] ?? '',
                pre_Ordem: h.po ?? '',
                transportadora: h.Transportadora ?? '',
                status: statusFinal,
                liberacao: h.cl ?? '',
                vistoriador: h.Vistoriador ?? '',
                pdf: h.Pdf ?? ''
              } as Historico;
            })
            .filter(Boolean) as Historico[];

          this.historico.set(dados);
          this.carregando.set(false);
        },
        error: () => {
          this.erro.set('Erro ao carregar o histórico.');
          this.carregando.set(false);
        }
      });
  }

  /* =======================
     Computed: filtro + ordenação
  ======================= */
  historicoFiltrado = computed(() => {
    const placaFiltro = this.normalizarPlaca(this.buscaPlaca());
    const transpFiltro = this.buscaTransp().trim().toUpperCase();

    const filtrado = this.historico().filter(h => {
      const placaHistorico = this.normalizarPlaca(h.placa);

      return (
        placaHistorico.includes(placaFiltro) &&
        h.transportadora.toUpperCase().includes(transpFiltro)
      );
    });

    return [...filtrado].sort((a, b) => {
      const dataA = this.parseDataHora(a.data, a.hora);
      const dataB = this.parseDataHora(b.data, b.hora);

      return this.ordemSelecionada() === 'asc'
        ? dataA - dataB
        : dataB - dataA;
    });
  });

  /* =======================
     Computed: contadores
  ======================= */
  totalCanceladas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Cancelada').length
  );

  totalConcluidas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Concluida').length
  );

  /* =======================
     Helpers
  ======================= */
  private parseDataHora(data: string, hora: string): number {
    if (!data) return 0;

    const [dia, mes, ano] = data.split('/').map(Number);
    const [hh = 0, mm = 0] = (hora ?? '').split(':').map(Number);

    return new Date(ano, mes - 1, dia, hh, mm).getTime();
  }
  /* =======================
     Placa helpers (formatação)
  ======================= */
  private normalizarPlaca(valor: string): string {
    return valor
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');
  }
  /* =======================
     Modal PDF
  ======================= */
  modalAberto = signal(false);
  pdfSelecionado = signal<string | null>(null);

  abrirPdf(pdfUrl: string): void {
    if (!pdfUrl) return;

    // força visualização no Drive
    const url = pdfUrl.includes('preview')
      ? pdfUrl
      : pdfUrl.replace('/view', '/preview');

    this.pdfSelecionado.set(url);
    this.modalAberto.set(true);
  }

  fecharModal(): void {
    this.modalAberto.set(false);
    this.pdfSelecionado.set(null);
  }


  formatarPlacaInput(valor: string): void {
    const limpa = this.normalizarPlaca(valor);

    if (limpa.length <= 3) {
      this.buscaPlaca.set(limpa);
      return;
    }

    const formatada = `${limpa.slice(0, 3)}-${limpa.slice(3, 7)}`;
    this.buscaPlaca.set(formatada);
  }

  /* =======================
     Navigation
  ======================= */
  voltar(): void {
    this.router.navigate(['/']);
  }
}
