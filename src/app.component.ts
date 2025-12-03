import { Component, ChangeDetectionStrategy, signal } from '@angular/core';
import { FormComponent } from './components/form/form.component';
import { PainelComponent } from './components/painel/painel.component';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormComponent, PainelComponent]
})
export class AppComponent {
  readonly view = signal<'list' | 'form'>('list');
  readonly selectedPlaca = signal<string | null>(null);

  onInspectionSelected(placa: string): void {
    this.selectedPlaca.set(placa);
    this.view.set('form');
  }

  goBack(): void {
    this.selectedPlaca.set(null);
    this.view.set('list');
  }
}