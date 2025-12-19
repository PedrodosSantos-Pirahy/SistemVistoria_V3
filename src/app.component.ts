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
  readonly view = signal<'list' | 'form' | 'agendar'>('list');

  // usado quando abre o formulário de vistoria
  readonly selectedPlaca = signal<string | null>(null);

  // navegação pela navbar
  setView(view: 'list' | 'agendar'): void {
    this.selectedPlaca.set(null);
    this.view.set(view);
  }
  


  // chamado pelo Painel ao clicar numa vistoria
  onInspectionSelected(placa: string) {
  setTimeout(() => {
    this.selectedPlaca.set(placa);
    this.view.set('form');
  });
}

  // voltar do formulário para o painel
  goBack(): void {
    this.selectedPlaca.set(null);
    this.view.set('list');
  }
}
