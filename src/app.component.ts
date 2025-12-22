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

  // usado quando abre o formulário de vistoria
  readonly selectedPlaca = signal<string | null>(null);

  // navegação pela navbar
  setView(view: 'list' ): void {
    this.selectedPlaca.set(null);
    this.view.set(view);
  }
  placaSelecionada: string | null = null;

onPlacaSelecionada = (placa: string) => {
  this.placaSelecionada = placa;
};

  


  // chamado pelo Painel ao clicar numa vistoria
  onInspectionSelected(placa: string) {
  this.selectedPlaca.set(placa);
  this.view.set('form');
}

  // voltar do formulário para o painel
  goBack(): void {
    this.selectedPlaca.set(null);
    this.view.set('list');
  }
}
