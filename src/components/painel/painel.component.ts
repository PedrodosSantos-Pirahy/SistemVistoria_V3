import { Component, ChangeDetectionStrategy, output, signal, OnInit } from '@angular/core';

interface Inspection {
  placa: string;
}

@Component({
  selector: 'app-painel',
  templateUrl: './painel.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PainelComponent implements OnInit {
  
  readonly inspections = signal<Inspection[]>([]);
  readonly loading = signal<boolean>(true);
  readonly error = signal<string | null>(null);
  
  readonly inspectionSelected = output<string>();

  ngOnInit(): void {
    this.fetchInspections();
  }

  async fetchInspections(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      // Fetches data from the local Python backend using POST
    const response = await fetch('http://127.0.0.1:5000/pendencias', {
  method: 'GET'
});

      if (!response.ok) {
        throw new Error(`Erro de servidor: ${response.statusText} (${response.status})`);
      }
      const data = await response.json();
      
      const placas = data.pendentes;

      if (!Array.isArray(placas)) {
        console.error('A resposta da API não é um array válido:', placas);
        throw new Error('Formato de dados inesperado da API. A lista de vistorias não foi encontrada.');
      }

      // The API now returns a simple array of plate strings.
      const parsedInspections: Inspection[] = placas
        .map((placa: unknown) => {
            if (typeof placa !== 'string' || !placa) {
                console.warn(`Item de vistoria inválido (não é string) ignorado:`, placa);
                return null;
            }
            return { placa };
        })
        .filter((item): item is Inspection => item !== null);


      this.inspections.set(parsedInspections);
    } catch (err) {
      console.error('Erro ao buscar dados da API:', err);
      let errorMessage = 'Não foi possível carregar as vistorias.';
      if (err instanceof Error) {
        // More specific message for fetch errors
        errorMessage = `Não foi possível conectar à API. Verifique se o backend em http://127.0.0.1:5000 está rodando. Detalhes: ${err.message}`;
      }
      this.error.set(errorMessage);
      this.inspections.set([]); // Ensure inspections list is empty on error
    } finally {
      this.loading.set(false);
    }
  }

  selectInspection(placa: string): void {
    this.inspectionSelected.emit(placa);
  }
}