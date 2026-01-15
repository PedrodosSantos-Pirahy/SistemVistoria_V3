import { Component, ChangeDetectionStrategy, signal } from '@angular/core';
import { FormComponent } from './components/form/form.component';
import { PainelComponent } from './components/painel/painel.component';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormComponent,
    PainelComponent,
  ]
})
export class AppComponent {

  // controla qual tela aparece (mesma rota)
  readonly view = signal<'list' | 'form'>('list');

  // vistoria selecionada (ID técnico + placa para exibição)
  readonly selectedInspection = signal<{
  placa: string;
  id: string;
} | null>(null);


  // navegação pela navbar
  setView(view: 'list'): void {
    this.selectedInspection.set(null);
    this.view.set(view);
  }

  // chamado pelo Painel ao clicar numa vistoria
  onInspectionSelected(inspection: { placa: string; id: string }) {
  console.log('APP RECEBEU:', inspection);

  this.selectedInspection.set({
    placa: inspection.placa,
    id: inspection.id
  });

  this.view.set('form');
}


  // usado apenas para exibição no template (placa)
  get placaSelecionada(): string | null {
    return this.selectedInspection()?.placa ?? null;
  }

  // voltar do formulário para o painel
  goBack(): void {
    this.selectedInspection.set(null);
    this.view.set('list');
  }
}
