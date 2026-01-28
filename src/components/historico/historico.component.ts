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
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

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
  pdf: string; // 👉 agora é SÓ O ID
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
  private sanitizer = inject(DomSanitizer);

  /* =======================
     State
  ======================= */
  historico = signal<Historico[]>([]);
  buscaPlaca = signal('');
  buscaTransp = signal('');
  ordemSelecionada = signal<'asc' | 'desc'>('desc');

  carregando = signal(false);
  erro = signal<string | null>(null);

  modalAberto = signal(false);
  pdfSelecionado = signal<SafeResourceUrl | null>(null);

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

    this.http.get<any>('http://192.168.53.193:5002/historico')
      .subscribe({
        next: res => {
          const dados: Historico[] = (res?.historico ?? [])
            .map((h: any) => {
              const status = (h.vr ?? '').toLowerCase().trim();

              if (!['concluida', 'concluído', 'cancelada', 'cancelado'].includes(status)) {
                return null;
              }

              return {
                id: `${h.Placa}-${h.Data}-${h['Hora Inicio']}`,
                placa: (h.Placa ?? '').toUpperCase(),
                data: h.Data ?? '',
                hora: h['Hora Inicio'] ?? '',
                pre_Ordem: h.po ?? '',
                transportadora: h.Transportadora ?? '',
                status: status.startsWith('conclu') ? 'Concluida' : 'Cancelada',
                liberacao: h.cl ?? '',
                vistoriador: h.Vistoriador ?? '',
                pdf: h.PDF ?? '' // 👉 SÓ O ID
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
     Computed
  ======================= */
  historicoFiltrado = computed(() => {
    const placaFiltro = this.normalizarPlaca(this.buscaPlaca());
    const transpFiltro = this.buscaTransp().toUpperCase();

    return [...this.historico()]
      .filter(h =>
        this.normalizarPlaca(h.placa).includes(placaFiltro) &&
        h.transportadora.toUpperCase().includes(transpFiltro)
      )
      .sort((a, b) => {
        const da = this.parseDataHora(a.data, a.hora);
        const db = this.parseDataHora(b.data, b.hora);
        return this.ordemSelecionada() === 'asc' ? da - db : db - da;
      });
  });

  totalCanceladas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Cancelada').length
  );

  totalConcluidas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Concluida').length
  );

  /* =======================
     PDF
  ======================= */
abrirPdf(valor: string): void {
  if (!valor) return;

  let fileId = valor.trim();

  // 🧠 Se vier URL completa, extrai o ID
  const match = fileId.match(/\/d\/([^/]+)/) || fileId.match(/id=([^&]+)/);
  if (match) {
    fileId = match[1];
  }

  // 🔥 SEMPRE gera preview padrão
  const previewUrl = `https://drive.google.com/file/d/${fileId}/preview`;

  this.pdfSelecionado.set(
    this.sanitizer.bypassSecurityTrustResourceUrl(previewUrl)
  );
  this.modalAberto.set(true);
}


  fecharModal(): void {
    this.modalAberto.set(false);
    this.pdfSelecionado.set(null);
  }

  /* =======================
     Helpers
  ======================= */
  private parseDataHora(data: string, hora: string): number {
    const [d, m, y] = data.split('/').map(Number);
    const [hh = 0, mm = 0] = (hora ?? '').split(':').map(Number);
    return new Date(y, m - 1, d, hh, mm).getTime();
  }

  private normalizarPlaca(v: string): string {
    return v.toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  formatarPlacaInput(valor: string): void {
    const limpa = this.normalizarPlaca(valor);
    this.buscaPlaca.set(
      limpa.length > 3 ? `${limpa.slice(0, 3)}-${limpa.slice(3, 7)}` : limpa
    );
  }

  voltar(): void {
    this.router.navigate(['/']);
  }
}
