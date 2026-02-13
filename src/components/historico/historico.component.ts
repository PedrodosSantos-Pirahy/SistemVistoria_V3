import {
  Component,
  ChangeDetectionStrategy,
  signal,
  OnInit,
  inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

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
  observacoes?: string;
}

@Component({
  selector: 'app-historico',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historico.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class HistoricoComponent implements OnInit {

  private http: HttpClient = inject(HttpClient);
  private sanitizer: DomSanitizer = inject(DomSanitizer);

  // DADOS DA PÁGINA ATUAL
  historico = signal<Historico[]>([]);

  // CONTROLE DE PAGINAÇÃO
  paginaAtual = signal(1);
  itensPorPagina = signal(10); // 10 itens por vez é ideal para mobile
  totalItens = signal(0);
  totalPaginas = signal(1);

  // FILTROS (Vão para o Backend)
  buscaPlaca = signal('');
  buscaTransp = signal('');
  
  carregando = signal(false);
  erro = signal<string | null>(null);

  // MODAL PDF
  modalAberto = signal(false);
  pdfSelecionado = signal<SafeResourceUrl | null>(null);

  ngOnInit(): void {
     this.buscarHistorico();
  }

  // BUSCA NO SERVIDOR (PAGINADA)
  buscarHistorico(): void {
     this.carregando.set(true);
     this.erro.set(null);

     const page = this.paginaAtual();
     const limit = this.itensPorPagina();
     const placa = this.normalizar(this.buscaPlaca());
     const transp = this.buscaTransp().toUpperCase();

     // Envia tudo para o Python processar
     const url = `http://192.168.53.193:5002/historico?page=${page}&limit=${limit}&placa=${placa}&transportadora=${transp}`;

     this.http.get<any>(url).subscribe({
         next: res => {
            // Mapeia os dados
            const dados: Historico[] = (res.data || []).map((h: any) => ({
                 id: h.id,
                 placa: h.placa,
                 data: h.data,
                 hora: h.hora,
                 pre_Ordem: h.po,
                 transportadora: h.transportadora,
                 status: h.status,
                 liberacao: h.liberado,
                 vistoriador: h.vistoriador,
                 pdf: h.pdf,
                 observacoes: h.observacoes
            }));
            
            this.historico.set(dados);
            
            // Atualiza rodapé da paginação
            if (res.meta) {
                this.totalItens.set(res.meta.total_items);
                this.totalPaginas.set(res.meta.total_pages);
            }
            
            this.carregando.set(false);
         },
         error: () => {
           this.erro.set('Erro ao carregar dados.');
           this.carregando.set(false);
         }
       });
  }

  // AÇÕES
  aoPesquisar() {
      this.paginaAtual.set(1); // Volta pra pag 1 ao filtrar
      this.buscarHistorico();
  }

  mudarPagina(novaPagina: number) {
    if (novaPagina >= 1 && novaPagina <= this.totalPaginas()) {
      this.paginaAtual.set(novaPagina);
      this.buscarHistorico();
    }
  }

  // PDF
  abrirPdf(idVistoria: string): void {
    if (!idVistoria) return;
    const urlPdf = `http://192.168.53.193:5002/pdf/${idVistoria}`;
    this.pdfSelecionado.set(this.sanitizer.bypassSecurityTrustResourceUrl(urlPdf));
    this.modalAberto.set(true);
  }

  fecharModal() {
     this.modalAberto.set(false);
     this.pdfSelecionado.set(null);
  }

  // HELPER
  private normalizar(v: string): string {
     return v ? v.toUpperCase().replace(/[^A-Z0-9]/g, '') : '';
  }
  
  formatarPlacaInput(valor: string): void {
     const limpa = this.normalizar(valor);
     this.buscaPlaca.set(
        limpa.length > 3 ? `${limpa.slice(0, 3)}-${limpa.slice(3, 7)}` : limpa
     );
  }
}