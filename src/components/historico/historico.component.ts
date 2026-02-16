import {
  Component,
  ChangeDetectionStrategy,
  signal,
  OnInit,
  inject
} from '@angular/core';
import { ApiService } from '../../services/app.service';
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

  private apiService: ApiService = inject(ApiService);
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

readonly tipoLocal = signal<'Qualquer' | 'Matriz' | 'Filial'>('Qualquer');

ngOnInit(): void {
    // 2. Configura o filtro baseado no usuário logado
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
        const user = JSON.parse(dados);
        if (user.local && (user.local === 'Matriz' || user.local === 'Filial')) {
            this.tipoLocal.set(user.local);
        }
    }
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
     const local = this.tipoLocal();

     // Envia tudo para o Python processar
     this.apiService.getHistorico(page, limit, placa, transp, local).subscribe({
         next: res => {
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
  // 4. Helper para trocar o local
setLocal(local: 'Qualquer' | 'Matriz' | 'Filial') {
    this.tipoLocal.set(local);
    this.paginaAtual.set(1);
    this.buscarHistorico();
}

  aoPesquisar() {
      this.paginaAtual.set(1); // Volta pra pag 1 ao filtrar
      this.buscarHistorico();
  }

// No arquivo: src/components/historico/historico.component.ts

mudarPagina(novaPagina: number) {
  if (novaPagina >= 1 && novaPagina <= this.totalPaginas()) {
    // 1. Atualiza o estado da página
    this.paginaAtual.set(novaPagina);
    
    // 2. Busca os novos dados no servidor
    this.buscarHistorico();

    // 🚀 3. VOLTA PARA O TOPO (A mágica acontece aqui)
    window.scrollTo({
      top: 0,
      behavior: 'smooth' // Faz a subida de forma suave em vez de um "pulo" seco
    });
  }
}
  // PDF
abrirPdf(idVistoria: string): void {
    if (!idVistoria) return;
    // SUBSTITUÍDO: Usa o helper do serviço para pegar a URL correta
    const urlPdf = this.apiService.getPdfUrl(idVistoria);
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