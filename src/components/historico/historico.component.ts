import { Component, ChangeDetectionStrategy, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

interface Historico {
  placa: string;
  data: string;
  hora: string;
  status: 'Expirado' | 'Concluida';
}

@Component({
  selector: 'app-historico',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './historico.component.html'
})
export class HistoricoComponent {

  historico = signal<Historico[]>([]);
  buscaPlaca = signal('');
  statusSelecionado = signal<'Todos' | 'Expirado' | 'Concluida'>('Todos');

  historicoFiltrado = computed(() => {
    return this.historico().filter(h => {
      const placaOk = h.placa.includes(this.buscaPlaca().toUpperCase());
      const statusOk =
        this.statusSelecionado() === 'Todos' || h.status === this.statusSelecionado();
      return placaOk && statusOk;
    });
  });

  // ✅ Adicione computeds para contar status
  totalExpiradas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Expirado').length
  );

  totalConcluidas = computed(() =>
    this.historicoFiltrado().filter(h => h.status === 'Concluida').length
  );

  constructor(private router: Router) {}

  voltar() {
    this.router.navigate(['/']);
  }
}