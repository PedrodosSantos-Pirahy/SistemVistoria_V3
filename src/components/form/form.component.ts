import { Component, ChangeDetectionStrategy, signal, OnDestroy, WritableSignal, ViewChild, ElementRef, input, effect, computed } from '@angular/core';
import { ReactiveFormsModule, FormGroup, FormControl, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';

declare var SignaturePad: any;

interface FormStep {
  number: number;
  name: string;
  groups: string[];
}

@Component({
  selector: 'app-form',
  templateUrl: './form.component.html',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class FormComponent implements OnDestroy {
  
  placa = input<string | null>(null);

  @ViewChild('controleQualidadeCanvas') controleQualidadeCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('motoristaCanvas') motoristaCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('vistoriadorCanvas') vistoriadorCanvas?: ElementRef<HTMLCanvasElement>;

  private cqPad: any;
  private motoristaPad: any;
  private vistoriadorPad: any;

  private veiculoSubscription: Subscription | undefined;

  readonly form = new FormGroup({
    dadosIniciais: new FormGroup({
      chegada: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      vistoria: new FormControl({ value: '', disabled: true }, { nonNullable: true, validators: [Validators.required] }),
      fim: new FormControl('', { nonNullable: true }),
      numeroOrdem: new FormControl('', { nonNullable: true }),
      transportadora: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      operacao: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      produto: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      ultimosProdutos: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      tipoVeiculo: new FormControl('', { nonNullable: true, validators: [Validators.required] })
    }),
    inspecaoInterna: new FormGroup({
      limpeza: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      danos: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      umidade: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      residuos: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      odores: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      bocasGraneleiras: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      lonas: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      chapasMdf: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
    }),
    protecaoCarga: new FormGroup({
      lonasProtecao: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      equipamentos: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
      tampasLaterais: new FormGroup({
        status: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        outro: new FormControl('', { nonNullable: true })
      }),
    }),
    detalhesVeiculo: new FormGroup({
      caminhaoBau: new FormGroup({
        alturaPorta: new FormGroup({
          status: new FormControl('', { nonNullable: true }),
          outro: new FormControl('', { nonNullable: true })
        }),
        larguraPorta: new FormGroup({
          status: new FormControl('', { nonNullable: true }),
          outro: new FormControl('', { nonNullable: true })
        }),
        assoalhoLiso: new FormGroup({
          status: new FormControl('', { nonNullable: true }),
          outro: new FormControl('', { nonNullable: true })
        }),
      }),
      container: new FormGroup({
        verificacaoPeso: new FormGroup({
          status: new FormControl('', { nonNullable: true }),
          outro: new FormControl('', { nonNullable: true })
        }),
      })
    }),
    fotosVistoria: new FormGroup({
      placas: new FormGroup({
        placa1: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        fotoPlaca1: new FormControl<string | null>(null, Validators.required),
        placa2: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
        fotoPlaca2: new FormControl<string | null>(null, Validators.required),
        placa3: new FormControl('', { nonNullable: true }),
        fotoPlaca3: new FormControl<string | null>(null),
      }),
      interiorCarroceria: new FormGroup({
        fotoInterior1: new FormControl<string | null>(null, Validators.required),
        fotoInterior2: new FormControl<string | null>(null),
      }),
    }),
    finalizacao: new FormGroup({
      controleQualidadeNome: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      controleQualidadeAssinatura: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      motoristaNome: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      motoristaAssinatura: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      vistoriadorNome: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      vistoriadorAssinatura: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      caminhaoLiberado: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      observacoes: new FormControl('', { nonNullable: true })
    })
  });

  readonly currentStep = signal(1);
  readonly steps: FormStep[] = [
    { number: 1, name: 'Dados Iniciais', groups: ['dadosIniciais'] },
    { number: 2, name: 'Inspeção Interna', groups: ['inspecaoInterna'] },
    { number: 3, name: 'Proteção Carga', groups: ['protecaoCarga'] },
    { number: 4, name: 'Detalhes e Fotos', groups: ['detalhesVeiculo', 'fotosVistoria'] },
    { number: 5, name: 'Finalização', groups: ['finalizacao'] },
  ];
  readonly totalSteps = this.steps.length;
  readonly currentStepName = computed(() => this.steps[this.currentStep() - 1]?.name || '');

  readonly tiposVeiculo = ['Baú', 'Caçamba', 'Carroceria', 'Sider', 'Graneleiro', 'Container', 'Tanque'];
  readonly submittedData = signal<string | null>(null);
  readonly isSubmitting = signal(false);
  readonly submissionError = signal<string | null>(null);

  // Signals for image previews
  readonly placa1Preview = signal<string | null>(null);
  readonly placa2Preview = signal<string | null>(null);
  readonly placa3Preview = signal<string | null>(null);
  readonly interior1Preview = signal<string | null>(null);
  readonly interior2Preview = signal<string | null>(null);

  constructor() {
    effect(() => {
      const currentPlaca = this.placa();
      if (currentPlaca) {
        this.form.controls.fotosVistoria.controls.placas.controls.placa1.setValue(currentPlaca);
      }
    });

    this.veiculoSubscription = this.form.controls.dadosIniciais.controls.tipoVeiculo.valueChanges.subscribe(value => {
      this.updateValidators(value);
    });

    effect(() => {
      if (this.currentStep() === this.totalSteps) {
        // Timeout to allow canvas elements to be rendered before initializing
        setTimeout(() => this.initializeSignaturePads(), 0);
      }
    });
  }

  ngOnDestroy(): void {
    this.veiculoSubscription?.unsubscribe();
  }

  private initializeSignaturePads(): void {
    if (!this.controleQualidadeCanvas || !this.motoristaCanvas || !this.vistoriadorCanvas) return;

    const options = {
        penColor: 'black',
        backgroundColor: 'rgb(249 250 251)', // bg-gray-50
    };
    
    this.cqPad = new SignaturePad(this.controleQualidadeCanvas.nativeElement, options);
    this.motoristaPad = new SignaturePad(this.motoristaCanvas.nativeElement, options);
    this.vistoriadorPad = new SignaturePad(this.vistoriadorCanvas.nativeElement, options);

    this.cqPad.addEventListener("endStroke", () => {
        this.form.controls.finalizacao.controls.controleQualidadeAssinatura.setValue(this.cqPad.toDataURL());
    });
    this.motoristaPad.addEventListener("endStroke", () => {
        this.form.controls.finalizacao.controls.motoristaAssinatura.setValue(this.motoristaPad.toDataURL());
    });
    this.vistoriadorPad.addEventListener("endStroke", () => {
        this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue(this.vistoriadorPad.toDataURL());
    });
  }

  limparAssinatura(pad: 'cq' | 'motorista' | 'vistoriador'): void {
    switch(pad) {
        case 'cq':
            this.cqPad?.clear();
            this.form.controls.finalizacao.controls.controleQualidadeAssinatura.setValue('');
            break;
        case 'motorista':
            this.motoristaPad?.clear();
            this.form.controls.finalizacao.controls.motoristaAssinatura.setValue('');
            break;
        case 'vistoriador':
            this.vistoriadorPad?.clear();
            this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue('');
            break;
    }
  }

  private updateValidators(tipoVeiculo: string): void {
    const isBau = tipoVeiculo === 'Baú';
    const isContainer = tipoVeiculo === 'Container';
  
    const bauControls = this.form.controls.detalhesVeiculo.controls.caminhaoBau.controls;
    this.setRequired(bauControls.alturaPorta.controls.status, isBau);
    this.setRequired(bauControls.larguraPorta.controls.status, isBau);
    this.setRequired(bauControls.assoalhoLiso.controls.status, isBau);
  
    const containerControls = this.form.controls.detalhesVeiculo.controls.container.controls;
    this.setRequired(containerControls.verificacaoPeso.controls.status, isContainer);
  }

  private setRequired(control: FormControl, isRequired: boolean): void {
    if (isRequired) {
      control.setValidators(Validators.required);
    } else {
      control.clearValidators();
      control.reset('');
    }
    control.updateValueAndValidity();
  }

  private getFormattedTimestamp(): string {
    return new Date().toLocaleString('pt-BR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  registrarVistoria() {
    this.form.controls.dadosIniciais.controls.vistoria.setValue(this.getFormattedTimestamp());
  }

  onFileChange(event: Event, controlPath: string, previewSignal: WritableSignal<string | null>): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];

    const control = this.form.get(controlPath);
    if (!control) return;

    if (file) {
      control.markAsTouched();
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        previewSignal.set(result);
        control.setValue(result);
      };
      reader.readAsDataURL(file);
    } else {
      control.setValue(null);
      previewSignal.set(null);
    }
  }

  isCurrentStepValid(): boolean {
    const currentStepInfo = this.steps[this.currentStep() - 1];
    if (!currentStepInfo) return false;

    return currentStepInfo.groups.every(groupName => {
        const currentGroup = this.form.get(groupName);
        return currentGroup ? currentGroup.valid : false;
    });
  }

  previousStep(): void {
    if (this.currentStep() > 1) {
        this.currentStep.update(s => s - 1);
    }
  }

  nextStep(): void {
      if (this.isCurrentStepValid()) {
          if (this.currentStep() < this.totalSteps) {
              this.currentStep.update(s => s + 1);
          }
      } else {
          const currentStepInfo = this.steps[this.currentStep() - 1];
          currentStepInfo.groups.forEach(groupName => {
               const currentGroup = this.form.get(groupName) as FormGroup;
               if(currentGroup) currentGroup.markAllAsTouched();
          });
      }
  }

  private processFormValue(value: any): any {
    const processedValue = JSON.parse(JSON.stringify(value)); // Deep copy to avoid mutating form state

    const processGroup = (group: any) => {
      if (!group) return;
      for (const key in group) {
        // Check if it's a question group like { status: '...', outro: '...' }
        if (group[key] && typeof group[key] === 'object' && 'status' in group[key]) {
          // If 'Outro' is selected, replace 'status' with the text from 'outro'
          if (group[key].status === 'Outro') {
            group[key].status = group[key].outro || '';
          }
          // The backend expects an object with a 'status' property, so we just remove the 'outro' field.
          delete group[key].outro;
        }
      }
    };

    processGroup(processedValue.inspecaoInterna);
    processGroup(processedValue.protecaoCarga);

    if (processedValue.detalhesVeiculo) {
      processGroup(processedValue.detalhesVeiculo.caminhaoBau);
      processGroup(processedValue.detalhesVeiculo.container);
    }

    return processedValue;
  }

  async onSubmit() {
    this.form.markAllAsTouched();
    if (!this.form.valid) {
      console.error('Formulário inválido.');
      return;
    }

    this.isSubmitting.set(true);
    this.submissionError.set(null);
    this.submittedData.set(null);

    try {
        this.form.controls.dadosIniciais.controls.fim.setValue(this.getFormattedTimestamp());
        
        const rawValue = this.form.getRawValue();
        const payload = this.processFormValue(rawValue);

        // Send the request as JSON
        const response = await fetch('http://127.0.0.1:5000/vistoria', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            let errorBody;
            try {
                errorBody = await response.json();
            } catch (e) {
                errorBody = await response.text();
            }
            throw new Error(`Erro no servidor: ${response.statusText} (${response.status}). Detalhes: ${typeof errorBody === 'string' ? errorBody : JSON.stringify(errorBody)}`);
        }

        const responseData = await response.json();
        console.log('Vistoria enviada com sucesso!', responseData);
        
        this.submittedData.set(JSON.stringify(payload, null, 2));
        window.scrollTo(0, 0);

    } catch (err) {
        console.error('Erro ao enviar formulário:', err);
        let errorMessage = 'Não foi possível enviar a vistoria.';
        if (err instanceof Error) {
            if (err.message.includes('Failed to fetch')) {
                errorMessage = `Não foi possível conectar à API. Verifique se o backend em http://127.0.0.1:5000 está rodando.`;
            } else {
                errorMessage = err.message;
            }
        }
        this.submissionError.set(errorMessage);
    } finally {
        this.isSubmitting.set(false);
    }
  }
}