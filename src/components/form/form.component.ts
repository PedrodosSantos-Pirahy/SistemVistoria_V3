///ng serve --host 192.168.53.193

import { Component, ChangeDetectionStrategy, signal, OnDestroy, WritableSignal, ViewChild, ElementRef, input, effect, computed, output } from '@angular/core';
import { ReactiveFormsModule, FormGroup, FormControl, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { OfflineStorageService } from '../../storange/offline-storage.service';
import { FormsModule } from '@angular/forms'; // Importante para ngModel


declare var SignaturePad: any;

interface FormStep {
  number: number;
  name: string;
  groups: string[];
}
interface OrdemTransportadora {
  pre_ordem: string;
  transportadora: string;
}
@Component({
  selector: 'app-form',
  templateUrl: './form.component.html',
  standalone:true,
  imports: [ReactiveFormsModule, CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class FormComponent implements OnDestroy {

  placa = input<string | null>(null);
  vistoriaId = signal<string | null>(null);





  @ViewChild('controleQualidadeCanvas') controleQualidadeCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('motoristaCanvas') motoristaCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('vistoriadorCanvas') vistoriadorCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('fullscreenSignatureCanvas') fullscreenCanvas!: ElementRef<HTMLCanvasElement>;


  private padMotorista: any = null;


  private padVistoriador: any = null;

  // Pad fullscreen temporário
  private fullscreenPad: any = null;

  private veiculoSubscription: Subscription | undefined;

  readonly form = new FormGroup({
    dadosIniciais: new FormGroup({
      chegada: new FormControl('', {
        nonNullable: true,
        validators: [
          Validators.required,
          control => {
            const value = control.value;
            if (!value) return null;

            const ano = Number(value.split('-')[0]);
            return ano > 9999 ? { anoInvalido: true } : null;
          }
        ]
      }),
      vistoria: new FormControl({ value: '', disabled: true }, { nonNullable: true, validators: [Validators.required] }),
      fim: new FormControl('', { nonNullable: true }),
      numeroOrdem: new FormControl('', { nonNullable: true }),
      transportadora: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      operacao: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      produto: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      ultimosProdutos: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      tipoVeiculo: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      localVistoria: new FormControl('', { nonNullable: true,validators: [Validators.required]})

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
  readonly showToast = signal(false);
  signatureFor: 'motorista' | 'vistoriador' | null = null;




  selectedPlaca() {
    const placa = this.form.get('fotosVistoria.placas.placa1')?.value;
    console.log('selectedPlaca:', placa);  // <-- aqui você vê o valor
    return placa;
  }
  async buscarOrdemETransportadoraPorPlaca(
    placaForm: string
  ): Promise<OrdemTransportadora | null> {
    try {
      // Adicione um timestamp para evitar cache
      const t = new Date().getTime();
      const response = await fetch(`http://192.168.53.193:5000/pendencias?t=${t}`);

      if (!response.ok) return null;

      const data = await response.json();
      const pendentes = data.pendentes || [];

      const placaNormalizada = placaForm.trim().toUpperCase();

      const encontrada = pendentes.find((p: any) => {
        if (!p?.placa) return false;
        // Pega só a placa, ignorando horário se tiver (ex: "10:00/AAA-1234")
        const placaApi = p.placa.includes('/') ? p.placa.split('/')[1] : p.placa;
        return placaApi?.trim().toUpperCase() === placaNormalizada;
      });

      if (!encontrada) return null;

      return {
        // O Python já manda todas as ordens concatenadas aqui
        pre_ordem: encontrada.pre_ordem || '', 
        // O Python já manda a transportadora do JOIN aqui
        transportadora: encontrada.transportadora || '' 
      };

    } catch (e) {
      console.error('Erro ao buscar dados:', e);
      return null;
    }
  }

 async buscarIdPorPlaca(placaForm: string): Promise<string | null> {
    try {
      const response = await fetch('http://192.168.53.193:5000/pendencias');
      if (!response.ok) return null;

      const data = await response.json();
      const pendentes = data?.pendentes ?? [];
      const placaNormalizada = placaForm.trim().toUpperCase();

      const encontrada = pendentes.find((p: any) => {
        if (!p?.placa) return false;
        const placaApi = p.placa.includes('/') ? p.placa.split('/')[1] : p.placa;
        return placaApi?.trim().toUpperCase() === placaNormalizada;
      });

      if (!encontrada) return null;

      console.log('✅ Pendência encontrada (Com Local):', encontrada);

      // 🔥 CORREÇÃO: SE TEM LOCAL NA PENDÊNCIA, USE ELE!
      if (encontrada.local) {
          // Normaliza: MATRIZ -> Matriz
          const localFormatado = encontrada.local.charAt(0).toUpperCase() + encontrada.local.slice(1).toLowerCase();
          
          if (['Matriz', 'Filial'].includes(localFormatado)) {
              console.log(`📍 Aplicando Local do Agendamento: ${localFormatado}`);
              this.form.get('dadosIniciais.localVistoria')?.setValue(localFormatado);
          }
      }

      return encontrada.id ?? null;

    } catch (e) {
      console.error('Erro ao buscar ID:', e);
      return null;
    }
  }

  updatePlaca(placaDoBanco: string) {
    if (!placaDoBanco) return;

    // Formata a placa caso tenha barra
    const placaFormatada = placaDoBanco.includes('/')
      ? placaDoBanco.split('/')[1]
      : placaDoBanco;

    // Atualiza o FormControl
    this.form.get('fotosVistoria.placas.placa1')?.setValue(placaFormatada, { emitEvent: false });

    console.log('Placa atualizada no formulário:', placaFormatada);
  }

  private placaInicializada = false;
  constructor(
    private router: Router,
    private offlineStorage: OfflineStorageService) {
    
    const userJson = localStorage.getItem('user');
    if (userJson) {
      try {
        const user = JSON.parse(userJson);
        if (user && user.local) {
          const localLimpo = user.local.toString().trim().toUpperCase();
          let valorFinal = '';
          if (localLimpo === 'MATRIZ') valorFinal = 'Matriz';
          else if (localLimpo === 'FILIAL') valorFinal = 'Filial';
          
          if (valorFinal) {
            this.form.get('dadosIniciais.localVistoria')?.setValue(valorFinal);
          }
        }
      } catch (e) {
        console.error('Erro ao ler usuario local', e);
      }
    }

    effect(async () => {
      if (this.placaInicializada) return;


      // Forçamos o tipo para evitar o erro falso do editor
      const placaRecebida = (this.placa as any)();
      if (!placaRecebida) return;

      const placaFormatada = placaRecebida.includes('/')
        ? placaRecebida.split('/')[1]
        : placaRecebida;

      const dados = await this.buscarOrdemETransportadoraPorPlaca(placaFormatada);

      if (!dados) {
        console.warn('⚠️ Ordem / transportadora não encontrada');
        return;
      }

      this.form.get('dadosIniciais.numeroOrdem')
        ?.setValue(dados.pre_ordem, { emitEvent: false });

      this.form.get('dadosIniciais.transportadora')
        ?.setValue(dados.transportadora, { emitEvent: false });

      // mantém exatamente o que você já fazia
      this.form
        .get('fotosVistoria.placas.placa1')
        ?.setValue(placaFormatada);
      try {
          console.log(`🔍 Buscando dados de carga para placa: ${placaFormatada}`);
          const resp = await fetch(`http://192.168.53.193:5000/dados-carga/${placaFormatada}`);
          
          if (resp.ok) {
              const dados = await resp.json();
              console.log('📦 Dados recebidos do Python:', dados); // OLHE ISSO NO CONSOLE DO NAVEGADOR (F12)
              
              if (dados.encontrado) {
                  const controls = this.form.controls.dadosIniciais.controls;
                  
                  // Preenche TRANSPORTADORA
                  if (dados.transportadora) {
                      controls.transportadora.setValue(dados.transportadora);
                      controls.transportadora.disable(); 
                  }

                  // Preenche PRODUTO
                  if (dados.produto) {
                      controls.produto.setValue(dados.produto);
                      controls.produto.disable(); 
                  } else {
                      // Se vier vazio, forçamos um texto
                      controls.produto.setValue("Produto não identificado no sistema");
                      controls.produto.disable();
                  }
                  
                  // Preenche ORDEM
                  if (dados.pre_ordem) {
                      controls.numeroOrdem.setValue(dados.pre_ordem);
                      controls.numeroOrdem.disable(); 
                  }
              }
          }
      } catch (err) {
          console.error("❌ Erro ao buscar dados da carga:", err);
      }

      // 🔑 NOVO: resolve o ID usando a placa
      const idEncontrado = await this.buscarIdPorPlaca(placaFormatada);
      
      if (!idEncontrado) {
        console.warn('⚠️ ID NÃO ENCONTRADO PARA A PLACA:', placaFormatada);
      } else {
        console.log('✅ ID RESOLVIDO:', idEncontrado);
      }

      this.vistoriaId.set(idEncontrado);

      this.placaInicializada = true;

      // 🔄 RESTAURA DRAFT SE EXISTIR
      const draft = await this.offlineStorage.buscarPorVistoriaId(idEncontrado);

      if (draft?.payload) {
        console.log('♻️ Draft encontrado. Restaurando formulário...');

        this.form.patchValue(draft.payload);
        this.currentStep.set(draft.stepAtual ?? 1);
        const fotos = draft.payload?.fotosVistoria;

        if (fotos?.placas?.fotoPlaca1) {
          this.placa1Preview.set(fotos.placas.fotoPlaca1);
        }
        if (fotos?.placas?.fotoPlaca2) {
          this.placa2Preview.set(fotos.placas.fotoPlaca2);
        }
        if (fotos?.placas?.fotoPlaca3) {
          this.placa3Preview.set(fotos.placas.fotoPlaca3);
        }
        if (fotos?.interiorCarroceria?.fotoInterior1) {
          this.interior1Preview.set(fotos.interiorCarroceria.fotoInterior1);
        }
        if (fotos?.interiorCarroceria?.fotoInterior2) {
          this.interior2Preview.set(fotos.interiorCarroceria.fotoInterior2);
        }

        setTimeout(() => {
          const motorista = this.form.controls.finalizacao.controls.motoristaAssinatura.value;
          const vistoriador = this.form.controls.finalizacao.controls.vistoriadorAssinatura.value;

          if (motorista && this.motoristaCanvas?.nativeElement) {
            this.renderSignatureToCanvas(this.motoristaCanvas.nativeElement, motorista);
          }

          if (vistoriador && this.vistoriadorCanvas?.nativeElement) {
            this.renderSignatureToCanvas(this.vistoriadorCanvas.nativeElement, vistoriador);
          }
        }, 300);

        alert('🔄 Encontramos uma vistoria em andamento. Seus dados foram restaurados.');
      }

    });



    // validação por tipo de veículo (continua igual)
    this.veiculoSubscription =
      this.form.controls.dadosIniciais.controls.tipoVeiculo.valueChanges
        .subscribe(value => this.updateValidators(value));

    window.addEventListener('online', () => {
      console.log('🌐 Internet restaurada');
      this.submissionError.set(null);
    });

    window.addEventListener('offline', () => {
      console.log('📴 Internet perdida');
    });

  }


  formatarPlaca(event: Event, controlName: 'placa1' | 'placa2' | 'placa3') {
    const input = event.target as HTMLInputElement;
    if (!input) return;

    let value = input.value
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');

    // Limita caracteres crus (sem hífen)
    value = value.slice(0, 7);

    // Aplica hífen após 3 caracteres
    if (value.length > 3) {
      value = value.slice(0, 3) + '-' + value.slice(3);
    }

    input.value = value;

    this.form
      .get('fotosVistoria.placas.' + controlName)
      ?.setValue(value, { emitEvent: false });
  }



  formatarPlacaControl(
    controlName: 'placa2' | 'placa3',
    event: Event
  ) {
    const input = event.target as HTMLInputElement;
    if (!input) return;

    let value = input.value
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');

    if (value.length > 3) {
      value = value.slice(0, 3) + '-' + value.slice(3);
    }

    if (value.length > 8) {
      value = value.slice(0, 8);
    }

    input.value = value;

    this.form
      .get(`fotosVistoria.placas.${controlName}`)
      ?.setValue(value, { emitEvent: false });
  }


  toDatetimeLocalWithSeconds(date: Date): string {
    const pad = (n: number) => n.toString().padStart(2, '0');

    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  ngOnDestroy(): void {
    this.veiculoSubscription?.unsubscribe();
  }

  ngOnInit() {
    console.log(
      'FORM CONTROL EXISTE:',
      this.form.get('fotosVistoria.placas.placa1')
    );

    this.form.valueChanges
      .pipe(debounceTime(500))
      .subscribe(() => {

        if (this.isSubmitting()) return;

        if (!this.vistoriaId()) return;

        const payloadCompleto = this.form.getRawValue(); // 🔑 CHAVE DO PROBLEMA

        this.offlineStorage.salvarResposta({
          vistoriaId: this.vistoriaId(),
          placa: payloadCompleto.fotosVistoria?.placas?.placa1,
          stepAtual: this.currentStep(),
          payload: payloadCompleto,
          atualizadoEm: new Date().toISOString(),
          sincronizado: false
        });
      });


  }


  // Estado
  showSignatureFullscreen = signal(false);


  activePad: 'motorista' | 'vistoriador' | null = null;
  activeCanvas: HTMLCanvasElement | null = null;
  signaturePreview: string | null = null;

  ngAfterViewInit(): void {
    // Inicializa os pads dos canvases que aparecem no formulário para que
    // já estejam prontos na primeira tentativa de assinatura.
    // Uso de setTimeout dá tempo pro Angular renderizar os canvases.
    setTimeout(() => this.inicializarPadsPrincipais(), 150);
  }

  getSavedSignature(which: 'motorista' | 'vistoriador') {
    if (which === 'motorista') {
      return this.form.controls.finalizacao.controls.motoristaAssinatura.value;
    }
    if (which === 'vistoriador') {
      return this.form.controls.finalizacao.controls.vistoriadorAssinatura.value;
    }
    return null;
  }

  private triggerToast(duration = 3000) {
    this.showToast.set(true);
    setTimeout(() => this.showToast.set(false), duration);
  }
  saveSignature() {
    if (!this.fullscreenPad || this.fullscreenPad.isEmpty()) return;

    const dataURL = this.fullscreenPad.toDataURL();
    if (this.signatureFor === 'motorista') {
      this.form.controls.finalizacao.controls.motoristaAssinatura.setValue(dataURL);
    }
    if (this.signatureFor === 'vistoriador') {
      this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue(dataURL);
    }

    if (dataURL) {
      alert('Assinatura salva! Pode fechar esta tela.');
    }
    window.addEventListener('online', () => {
      console.log('🌐 Internet restaurada');
      this.submissionError.set(null);
    });

    window.addEventListener('offline', () => {
      console.log('📴 Internet perdida');
    });


  }


  private inicializarPadsPrincipais(): void {
    try {

      if (this.motoristaCanvas?.nativeElement) {
        this.padMotorista = new SignaturePad(this.motoristaCanvas.nativeElement, {
          backgroundColor: 'white',
          penColor: 'black'
        });
        this.padMotorista.clear();
      }

      if (this.vistoriadorCanvas?.nativeElement) {
        this.padVistoriador = new SignaturePad(this.vistoriadorCanvas.nativeElement, {
          backgroundColor: 'white',
          penColor: 'black'
        });
        this.padVistoriador.clear();
      }
    } catch (e) {
      console.warn('Erro ao inicializar pads principais:', e);
    }
  }

  // Abre o canvas fullscreen para assinar
  openSignatureFullscreen(which: 'motorista' | 'vistoriador') {
    this.signatureFor = which;
    this.activePad = which;

    const container = document.getElementById('signatureFullscreen');
    if (container) {
      container.classList.remove('hidden'); // MOSTRA o modal
    }

    // aguarda o DOM renderizar
    setTimeout(() => {
      const canvas = this.fullscreenCanvas.nativeElement;
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;

      this.fullscreenPad = new SignaturePad(canvas, {
        minWidth: 1,
        maxWidth: 2,
        penColor: "black",
      });

      const saved = this.getSavedSignature(which);
      if (saved) {
        this.fullscreenPad.fromDataURL(saved);
      }
    }, 50);
  }



  // Gera preview imediado e salva no FormControl correspondente
  updatePreview() {
    if (!this.fullscreenPad || this.fullscreenPad.isEmpty()) return;

    const dataURL = this.fullscreenPad.toDataURL();
    this.signaturePreview = dataURL;

    try {
      if (this.activePad === 'motorista') {
        if (this.padMotorista && typeof this.padMotorista.fromDataURL === 'function') {
          this.padMotorista.clear();
          this.padMotorista.fromDataURL(dataURL);
        } else if (this.activeCanvas) {
          this.drawImageOnCanvas(this.activeCanvas, dataURL);
        }
        this.form.controls.finalizacao.controls.motoristaAssinatura.setValue(dataURL);
      } else if (this.activePad === 'vistoriador') {
        if (this.padVistoriador && typeof this.padVistoriador.fromDataURL === 'function') {
          this.padVistoriador.clear();
          this.padVistoriador.fromDataURL(dataURL);
        } else if (this.activeCanvas) {
          this.drawImageOnCanvas(this.activeCanvas, dataURL);
        }
        this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue(dataURL);
      }
    } catch (e) {
      console.error('Erro ao gerar preview:', e);
    }
  }

  // Utilitário para desenhar uma dataURL num canvas nativo
  private drawImageOnCanvas(target: HTMLCanvasElement, dataURL: string, callback?: () => void) {
    const img = new Image();
    img.src = dataURL;
    img.onload = () => {
      const displayW = target.offsetWidth;
      const displayH = target.offsetHeight;
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      target.width = Math.floor(displayW * ratio);
      target.height = Math.floor(displayH * ratio);
      target.style.width = `${displayW}px`;
      target.style.height = `${displayH}px`;

      const ctx = target.getContext('2d');
      if (!ctx) return;
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, displayW, displayH);
      ctx.drawImage(img, 0, 0, displayW, displayH);

      if (callback) callback();
    };
  }

  renderSignatureToCanvas(canvas: HTMLCanvasElement | null, dataURL: string) {
    if (!canvas) {
      setTimeout(() => this.renderSignatureToCanvas(canvas, dataURL), 50);
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setTimeout(() => this.renderSignatureToCanvas(canvas, dataURL), 50);
      return;
    }

    const img = new Image();
    img.src = dataURL;

    img.onload = () => {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
  }


  // Fecha o fullscreen e garante que a assinatura foi salva no canvas pequeno
  // fechar fullscreen — aceita param opcional
  async closeSignatureFullscreen(pad?: 'motorista' | 'vistoriador') {
    const container = document.getElementById('signatureFullscreen') as HTMLElement | null;
    // determina qual pad usar: argumento > estado interno
    const effectivePad = pad ?? this.activePad;

    // se não há pad e não há fullscreenPad, só fecha o fullscreen e limpa estado
    if (!container || !this.fullscreenPad) {
      try { if (document.fullscreenElement) await document.exitFullscreen(); } catch { }
      container?.classList.add('hidden');
      this.fullscreenPad = null;
      this.activePad = null;
      this.activeCanvas = null;
      return;
    }

    // Se ainda não sabemos qual pad usar, tenta usar activePad
    if (!effectivePad) {
      // só fecha e limpa
      try { if (document.fullscreenElement) await document.exitFullscreen(); } catch { }
      container.classList.add('hidden');
      this.fullscreenPad = null;
      this.activePad = null;
      this.activeCanvas = null;
      return;
    }

    // resolve control & canvas com base no pad efetivo
    let control: FormControl<string>;
    let targetCanvas: HTMLCanvasElement | null = null;

    switch (effectivePad) {
      case 'motorista':
        control = this.form.controls.finalizacao.controls.motoristaAssinatura;
        targetCanvas = this.motoristaCanvas?.nativeElement ?? null;
        break;
      case 'vistoriador':
      default:
        control = this.form.controls.finalizacao.controls.vistoriadorAssinatura;
        targetCanvas = this.vistoriadorCanvas?.nativeElement ?? null;
        break;
    }

    // se houver desenho, garante que foi salvo (updatePreview normalmente já fez isso)
    try {
      if (!this.fullscreenPad.isEmpty()) {
        const dataURL = this.fullscreenPad.toDataURL();
        control.setValue(dataURL);
        if (targetCanvas) this.drawImageOnCanvas(targetCanvas, dataURL);
      }
    } catch (e) {
      console.error('Erro ao copiar assinatura:', e);
    }

    // fecha fullscreen
    try { if (document.fullscreenElement) await document.exitFullscreen(); } catch { }

    // limpa pad fullscreen
    try { this.fullscreenPad.clear(); } catch (_) { }
    this.fullscreenPad = null;
    this.activePad = null;
    this.activeCanvas = null;
    container.classList.add('hidden');
  }

  clearSignature() {
    if (this.fullscreenPad) {
      this.fullscreenPad.clear();
    }
  }

  // Limpar assinatura — tanto do pad pequeno quanto do fullscreen (se presente)
  limparAssinatura(which: 'motorista' | 'vistoriador') {
    // limpa fullscreen também se estiver ativo
    try { this.fullscreenPad?.clear(); } catch (_) { }

    if (which === 'motorista') {
      try { this.padMotorista?.clear(); } catch (_) { }
      this.form.controls.finalizacao.controls.motoristaAssinatura.setValue('');
    } else if (which === 'vistoriador') {
      try { this.padVistoriador?.clear(); } catch (_) { }
      this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue('');
    }

    this.signaturePreview = null;
  }
  private getTargetCanvas(which: 'motorista' | 'vistoriador'): HTMLCanvasElement | null {
    switch (which) {
      case 'motorista': return this.motoristaCanvas?.nativeElement ?? null;
      case 'vistoriador': return this.vistoriadorCanvas?.nativeElement ?? null;
    }
  }

  private drawDataURLOnCanvas(canvas: HTMLCanvasElement, dataURL: string): Promise<void> {
    return new Promise((resolve) => {
      const tryDraw = () => {
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          requestAnimationFrame(tryDraw);
          return;
        }

        const img = new Image();
        img.src = dataURL;
        img.onload = () => {
          canvas.width = canvas.offsetWidth;
          canvas.height = canvas.offsetHeight;
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          resolve();
        };
      };
      tryDraw();
    });
  }


  async saveAndCloseSignature() {
    if (!this.fullscreenPad || !this.signatureFor) return;

    // Salva no FormControl
    const dataURL = this.fullscreenPad.toDataURL();
    if (this.signatureFor === 'motorista') {
      this.form.controls.finalizacao.controls.motoristaAssinatura.setValue(dataURL);
    } else if (this.signatureFor === 'vistoriador') {
      this.form.controls.finalizacao.controls.vistoriadorAssinatura.setValue(dataURL);
    }

    // Desenha no canvas pequeno de forma segura
    const targetCanvas = this.getTargetCanvas(this.signatureFor);
    if (targetCanvas) {
      await this.drawDataURLOnCanvas(targetCanvas, dataURL);
    }

    // Fecha o modal
    await this.closeSignatureFullscreen();
  }



  private getFormattedDatetimeLocal(date: Date): string {
    const pad = (n: number) => n.toString().padStart(2, '0');
    const yyyy = date.getFullYear().toString().slice(0, 4); // garante 4 dígitos
    const MM = pad(date.getMonth() + 1);
    const dd = pad(date.getDate());
    const hh = pad(date.getHours());
    const mm = pad(date.getMinutes());

    return `${dd}/${MM}/${yyyy}T${hh}:${mm}`;
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
    const now = new Date();
    this.form.controls.dadosIniciais.controls.vistoria.setValue(
      this.toDatetimeLocal(now)
    );
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
  private toDatetimeLocal(date: Date): string {
    const pad = (n: number) => n < 10 ? '0' + n : n;

    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
// Adicione este helper privado para rolar para o topo
  private scrollToTop() {
    // Rola a janela principal para o topo suavemente
    window.scrollTo({ top: 0, behavior: 'smooth' });
    
    // Se o formulário estiver dentro de um container com scroll (comum em layouts responsivos),
    // tente rolar esse container também.
    const mainContainer = document.querySelector('main'); 
    if (mainContainer) {
        mainContainer.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  previousStep(): void {
    if (this.currentStep() > 1) {
      this.currentStep.update(s => s - 1);
      this.scrollToTop();
    }
  }

nextStep(): void {
    if (this.isCurrentStepValid()) {
      if (this.currentStep() < this.totalSteps) {
        this.currentStep.update(s => s + 1);
        this.scrollToTop(); // Sucesso: Vai para o topo da próxima etapa
      }
    } else {
      const currentStepInfo = this.steps[this.currentStep() - 1];
      
      // 1. Marca tudo como "tocado" para aparecer os erros em vermelho
      currentStepInfo.groups.forEach(groupName => {
        const currentGroup = this.form.get(groupName) as FormGroup;
        if (currentGroup) currentGroup.markAllAsTouched();
      });
      
      alert('Existem campos obrigatórios não preenchidos nesta etapa.');

      // 2. 🔥 O PULO DO GATO: Rola para o primeiro erro encontrado
      setTimeout(() => {
        // Busca o primeiro elemento que tenha a classe de erro do Angular (.ng-invalid)
        // Ignoramos o próprio <form> para não rolar para o topo sem querer
        const primeiroErro = document.querySelector('.ng-invalid:not(form)');
        
        if (primeiroErro) {
          primeiroErro.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' // Centraliza o campo na tela
          });
          
          // Tenta dar foco (cursor) no campo, se for possível
          (primeiroErro as HTMLElement).focus();
        }
      }, 100); // 100ms de atraso para o DOM atualizar
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
  private formatarParaBanco(date: Date): string {
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} `
      + `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

private async podeEnviarParaApi(): Promise<boolean> {
  // 1. Verifica internet básica (Wifi/Dados)
  if (!navigator.onLine) {
    alert('Sem conexão de rede. Verifique o Wifi ou 4G.');
    return false;
  }
 
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 segundos timeout
 
    // 🔑 TRUQUE ANTI-CACHE:
    // Adicionamos ?t=... com a hora atual para o navegador achar que é uma url nova
    // e não usar a memória antiga.
    const timestamp = new Date().getTime();
    const urlTeste = `http://192.168.53.193:5000/pendencias?noCache=${timestamp}`;
 
    const resp = await fetch(urlTeste, {
      method: 'GET',
      cache: 'no-store', // Força não usar cache
      headers: { 
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      },
      signal: controller.signal
    });
 
    clearTimeout(timeoutId);
 
    if (resp.ok) {
      return true;
    } else {
      alert(`Servidor conectado, mas respondeu com erro: ${resp.status}`);
      return false;
    }
 
  } catch (error) {
    // Se caiu aqui, é porque falhou MESMO (timeout ou sem rede)
    alert('Falha ao conectar com o servidor (192.168.53.193). Verifique se ele está ligado.');
    return false;
  }
}
  
  readonly finished = output<void>();
 
  // 2. Método Principal de Envio (onSubmit)

// form.component.ts -> Substitua o método onSubmit por este ajustado

// No arquivo form.component.ts

async onSubmit() {
  this.form.markAllAsTouched();

  if (!this.form.valid) {
    alert('Existem campos obrigatórios não preenchidos. Verifique as abas em vermelho.');
    return;
  }

  // 1. TRAVA IMEDIATA (Evita clique duplo)
  this.isSubmitting.set(true);
  this.submissionError.set(null);

  // 2. Validação de Conexão
  const conexaoOk = await this.podeEnviarParaApi();
  if (!conexaoOk) {
    this.isSubmitting.set(false);
    return;
  }

  // 3. Preparação Visual
  // Avança a barra de progresso para 100% visualmente
  this.currentStep.update(() => this.totalSteps);
  this.submittedData.set(null);

  try {
    // 4. Formatação de Datas
    const nowStr = this.formatarParaBanco(new Date());
    // Atualiza o fim sem disparar eventos de formulário
    this.form.controls.dadosIniciais.controls.fim.setValue(nowStr, { emitEvent: false });

    // Pega os dados brutos do formulário
    const rawValue = this.form.getRawValue();

    // Formata datas de chegada/inicio se necessário
    let chegadaFmt = rawValue.dadosIniciais.chegada;
    if (chegadaFmt && !chegadaFmt.includes('/')) {
      chegadaFmt = this.formatarParaBanco(new Date(chegadaFmt));
    }
    
    let vistoriaFmt = rawValue.dadosIniciais.vistoria;
    if (vistoriaFmt && !vistoriaFmt.includes('/')) {
      vistoriaFmt = this.formatarParaBanco(new Date(vistoriaFmt));
    }

    // 5. CRIAÇÃO DO FORMDATA (O Segredo do Upload)
    const formData = new FormData();

    // --- A. CAMPOS DE TEXTO BÁSICOS ---
    formData.append('id', this.vistoriaId() || '');
    formData.append('chegada', chegadaFmt);
    formData.append('vistoria', vistoriaFmt);
    formData.append('fim', nowStr);
    formData.append('numeroOrdem', rawValue.dadosIniciais.numeroOrdem);
    formData.append('transportadora', rawValue.dadosIniciais.transportadora);
    formData.append('operacao', rawValue.dadosIniciais.operacao);
    formData.append('produto', rawValue.dadosIniciais.produto);
    formData.append('ultimosProdutos', rawValue.dadosIniciais.ultimosProdutos);
    formData.append('tipoVeiculo', rawValue.dadosIniciais.tipoVeiculo);
    formData.append('localVistoria', rawValue.dadosIniciais.localVistoria);
    formData.append('motoristaNome', rawValue.finalizacao.motoristaNome);
    formData.append('vistoriadorNome', rawValue.finalizacao.vistoriadorNome);
    formData.append('caminhaoLiberado', rawValue.finalizacao.caminhaoLiberado);
    formData.append('observacoes', rawValue.finalizacao.observacoes);


const placas = rawValue.fotosVistoria?.placas;
    
    if (placas?.placa1) {
        formData.append('placa1', placas.placa1);
    }

    if (placas?.placa2) {
        formData.append('placa2', placas.placa2);
    }
    
    if (placas?.placa3) {
        formData.append('placa3', placas.placa3);
    }
    // --- B. CHECKLIST (Achata os objetos {status: '...', outro: '...'} para texto simples) ---
    // Função auxiliar para pegar o valor correto (se for "Outro", pega o texto digitado)
    const getResposta = (grupo: any) => {
      return grupo.status === 'Outro' ? (grupo.outro || 'Outro (sem esp.)') : grupo.status;
    };

    // Inspeção Interna
    formData.append('limpeza', getResposta(rawValue.inspecaoInterna.limpeza));
    formData.append('danos', getResposta(rawValue.inspecaoInterna.danos));
    formData.append('umidade', getResposta(rawValue.inspecaoInterna.umidade));
    formData.append('residuos', getResposta(rawValue.inspecaoInterna.residuos));
    formData.append('odores', getResposta(rawValue.inspecaoInterna.odores));
    formData.append('bocasGraneleiras', getResposta(rawValue.inspecaoInterna.bocasGraneleiras));
    formData.append('lonas', getResposta(rawValue.inspecaoInterna.lonas));
    formData.append('chapasMdf', getResposta(rawValue.inspecaoInterna.chapasMdf));

    // Proteção Carga
    formData.append('lonasProtecao', getResposta(rawValue.protecaoCarga.lonasProtecao));
    formData.append('equipamentos', getResposta(rawValue.protecaoCarga.equipamentos));
    formData.append('tampasLaterais', getResposta(rawValue.protecaoCarga.tampasLaterais));

    // Detalhes Específicos (Baú / Container)
    if (rawValue.detalhesVeiculo?.caminhaoBau) {
      formData.append('alturaPorta', getResposta(rawValue.detalhesVeiculo.caminhaoBau.alturaPorta));
      formData.append('larguraPorta', getResposta(rawValue.detalhesVeiculo.caminhaoBau.larguraPorta));
      formData.append('assoalhoLiso', getResposta(rawValue.detalhesVeiculo.caminhaoBau.assoalhoLiso));
    }
    if (rawValue.detalhesVeiculo?.container) {
      formData.append('verificacaoPeso', getResposta(rawValue.detalhesVeiculo.container.verificacaoPeso));
    }

    // --- C. ARQUIVOS (Converte Base64 para Blob binário) ---
    
    // Função Helper Interna
    const dataURItoBlob = (dataURI: string | null) => {
      if (!dataURI || !dataURI.includes(',')) return null;
      const byteString = atob(dataURI.split(',')[1]);
      const mimeString = dataURI.split(',')[0].split(':')[1].split(';')[0];
      const ab = new ArrayBuffer(byteString.length);
      const ia = new Uint8Array(ab);
      for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
      return new Blob([ab], { type: mimeString });
    };

    // Fotos (JPG)
    const fotoP1 = dataURItoBlob(rawValue.fotosVistoria.placas.fotoPlaca1);
    if (fotoP1) formData.append('fotoPlaca1', fotoP1, 'placa1.jpg');

    const fotoP2 = dataURItoBlob(rawValue.fotosVistoria.placas.fotoPlaca2);
    if (fotoP2) formData.append('fotoPlaca2', fotoP2, 'placa2.jpg');

    const fotoP3 = dataURItoBlob(rawValue.fotosVistoria.placas.fotoPlaca3);
    if (fotoP3) formData.append('fotoPlaca3', fotoP3, 'placa3.jpg');

    const fotoInt1 = dataURItoBlob(rawValue.fotosVistoria.interiorCarroceria.fotoInterior1);
    if (fotoInt1) formData.append('fotoInterior1', fotoInt1, 'interior1.jpg');

    const fotoInt2 = dataURItoBlob(rawValue.fotosVistoria.interiorCarroceria.fotoInterior2);
    if (fotoInt2) formData.append('fotoInterior2', fotoInt2, 'interior2.jpg');

    // Assinaturas (PNG)
    const assMot = dataURItoBlob(rawValue.finalizacao.motoristaAssinatura);
    if (assMot) formData.append('assinaturaMotorista', assMot, 'motorista.png');

    const assVis = dataURItoBlob(rawValue.finalizacao.vistoriadorAssinatura);
    if (assVis) formData.append('assinaturaVistoriador', assVis, 'vistoriador.png');


    // 6. Limpeza do Rascunho (Antes de enviar para evitar conflito)
    const idParaRemover = this.vistoriaId();
    if (idParaRemover) {
      await this.offlineStorage.removerDraft(idParaRemover);
    }

    // 7. Envio para a API (Sem Header JSON, pois é Multipart)
    console.log('📤 Enviando FormData para o servidor...');
    
    fetch('http://192.168.53.193:5000/vistoria', {
      method: 'POST',
      body: formData, // O navegador define o boundary automaticamente
    })
    .then(async response => {
      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Servidor respondeu com erro: ${response.status} - ${errText}`);
      }
      return response.json();
    })
    .then(data => {
      console.log('✅ Sucesso Total:', data);
      alert('Vistoria enviada com sucesso!');
      this.finished.emit(); // Avisa o componente pai se necessário
      this.router.navigate(['/']); // Volta pro painel
    })
    .catch(err => {
      console.error('❌ Erro no envio:', err);
      alert(`Erro ao enviar vistoria: ${err.message}`);
      this.submissionError.set(err.message);
    })
    .finally(() => {
      this.isSubmitting.set(false);
    });

  } catch (error) {
    console.error('Erro crítico na preparação do envio:', error);
    alert('Ocorreu um erro interno ao preparar os dados.');
    this.isSubmitting.set(false);
  }
}
}