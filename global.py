# ------------------------------------------------------------------------------------
# Bibliotecas ------------------------------------------------------------------------

import numpy as np
from scipy.ndimage import generic_filter
import cv2
import random

import tkinter as tk
from tkinter import *
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# ------------------------------------------------------------------------------------
# Constantes -------------------------------------------------------------------------

NEIGHBOURHOOD_KERNEL_SIZE = 5 # Tamanho da vizinhança em que se pré-computa o desvio padrão no processo de transferência de cores
JITTER_SAMPLES = 200
JITTER_SAMPLES_M = int(np.ceil(np.sqrt(JITTER_SAMPLES)))
JITTER_SAMPLES_N = JITTER_SAMPLES_M

# ------------------------------------------------------------------------------------
# Definição das imagens envolvidas no processo de transferência de cores
source = None
target = None
result = None

# ------------------------------------------------------------------------------------
# Set Default Image ------------------------------------------------------------------

# Função que coloca a imagem default no display informado
def setDefaultImg(display):
    default = ImageTk.PhotoImage(file="img/default.jpg")
    display.config(image=default)
    display.image = default

# ------------------------------------------------------------------------------------
# Luminance Remapping ----------------------------------------------------------------

# Função que realiza o Luminance Remapping sobre a imagem A
def lumRemap(lumA, lumB):
   
   # Pega a média das luminâncias de ambas imagens
   meanA = np.mean(lumA)
   meanB = np.mean(lumB)

   # Pega o desvio padrão das luminâncias de ambas imagens
   stdA = np.std(lumA)
   stdB = np.std(lumB)

   # Evita divisão por zero
   if stdA == 0:
      stdA = 1
   stdB_A = stdB/stdA

   # Remapeia os valores da imagem A e retorna
   return stdB_A * (lumA - meanA) + meanB

# ------------------------------------------------------------------------------------
# Jitter Sampling --------------------------------------------------------------------

# Função para amostragem jitterizada e armazenamento de coordenadas
# Como funciona:
# - A imagem é dividida em uma grade de blocos de tamanho M×N.
# - Para cada bloco, um ponto é selecionado aleatoriamente dentro de seus limites. Isso é feito para evitar padrões fixos.
# Retorno: três arrays
# 1) Coordenadas de cada amostra na imagem original
# 2) Valor da luminância de cada amostra
# 3) Desvio padrão relativo a cada amostra (usa os valores pré-calculados e recebidos como argumento na função)
def jitterSampling(img, M, N, imgStd):

    # Cria vetores que armazenam coordenadas, valores de luminância e desvio padrão, respectivamente
    coord = []
    lum = []
    std = []

    # Calcula o tamanho dos passos a partir do tamanho dos blocos MxN indicados
    stepX = img.shape[0] // M  # Tamanho do passo em linhas
    stepY = img.shape[1] // N  # Tamanho do passo em colunas

    # Pega MxN amostras
    for i in range(M):
        for j in range(N):

            # Coordenada x aleatória
            x = random.randint(i * stepX, min((i + 1) * stepX - 1, img.shape[0] - 1))

            # Coordenada y aleatória
            y = random.randint(j * stepY, min((j + 1) * stepY - 1, img.shape[1] - 1))

            # Guarda as coordenadas, valores de luminância e desvio padrão
            coord.append((x, y))
            lum.append(img[x, y])
            std.append(imgStd[x, y])

    # Retorna os vetores
    return np.array(coord), np.array(lum), np.array(std)

# ------------------------------------------------------------------------------------
# Best Matching Color ----------------------------------------------------------------

# Função que encontra a melhor cor de match da imagem source a ser usada na imagem target com base em luminância (50%) e desvio padrão (50%)
def bestMatch(target, targetStd, source, sourceCoord, sourceStd):

    # Calcula uma "distância" para cada amostra, que é a soma das diferenças quadráticas entre as luminância e entre os desvios padrões.
    # Os pesos (50% cada) estão implícitos na fórmula, tratando igualmente as diferenças quadradas para luminância e desvio padrão.
    distances = (source - target)**2 + (sourceStd - targetStd)**2  # Distância ponderada

    # Retorna as coordenadas da melhor correspondência (menor distância)
    return sourceCoord[np.argmin(distances)]

# ------------------------------------------------------------------------------------
# Show Result Image ------------------------------------------------------------------

# Função que mostra na tela o resultado do processo de transferência de cores
def showResult(result, display):

    global NEIGHBOURHOOD_KERNEL_SIZE, JITTER_SAMPLES, JITTER_SAMPLES_M, JITTER_SAMPLES_N

    # Configura a imagem e o display indicado para mostra-la na tela.
    result = Image.fromarray(result)
    result = ImageTk.PhotoImage(result)
    display.config(image = result)
    display.image = result
    

# ------------------------------------------------------------------------------------
# Transferring Color to Greyscale Images ---------------------------------------------

# Algoritmo do processo de transferência de cores
def colorTransfer(display):
   global source, target, result
   
   # Verifica se as imagens foram selecionadas
   if source is not None and target is not None:
      
      # Converte a imagem source para o espaço de cores Lab
      sourceLab = cv2.cvtColor(source, cv2.COLOR_RGB2Lab)
      
      # Converte para tipo float64 para maior precisão
      sourceLab = sourceLab.astype(np.float64)
      targetLum = target.astype(np.float64)
      
      # Pega a luminância da imagem source
      sourceLum = sourceLab[:,:,0]
      
      # Realiza o Luminance Remapping sobre a imagem source
      sourceRemap = lumRemap(sourceLum, targetLum)
      
      # Caso haja valores negativos na nova luminância, ajusta os valores para serem inteiros não negativos
    #   sourceRemapMin = np.amin(sourceRemap)
    #   if sourceRemapMin < 0:
    #      sourceRemap = sourceRemap - sourceRemapMin
    #      sourceRemapMax = np.amax(sourceRemap)
    #      if sourceRemapMax == 0:
    #          sourceRemapMax = 1
    #      sourceRemap = sourceRemap * 255 / sourceRemapMax

      # Pré-computa o desvio padrão dos valores de luminância de vizinhanças 5x5 em cada imagem.
      sourceStd = generic_filter(sourceRemap, np.std, size = NEIGHBOURHOOD_KERNEL_SIZE)
      targetStd = generic_filter(target, np.std, size = NEIGHBOURHOOD_KERNEL_SIZE)

      # Realiza Jitter Sampling para diminuir o número de amostras necessárias da imagem source
      sourceSamplesCoord, sourceSamplesLum, sourceSamplesStd = jitterSampling(sourceRemap, JITTER_SAMPLES_M, JITTER_SAMPLES_N, sourceStd)

      # Configura variável que guarda o resultado do processo
      result = np.zeros((targetLum.shape[0], targetLum.shape[1], 3))  # Inicializa o array do resultado
      result[:, :, 0] = targetLum  # Copia o canal de luminância da imagem target

      # Loop para colorir cada pixel da imagem
      for i in range(result.shape[0]):
        for j in range(result.shape[1]):
           
           # Encontra a melhor cor de match para o pixel, onde a cor é dada pelos índices dos canais alfa e beta da imagem source
           [a, b] = bestMatch(result[i][j][0], targetStd[i][j], sourceSamplesLum, sourceSamplesCoord, sourceSamplesStd)

           # Pega os valores dos canais alfa e beta do pixel da imagem original
           alpha_channel = sourceLab[a][b][1]  # Canal alpha
           beta_channel = sourceLab[a][b][2]  # Canal beta

           # Salva os valores dos canais alfa e beta na imagem resultante
           result[i][j][1] = alpha_channel
           result[i][j][2] = beta_channel

      # Configura imagem do resultado
      result = result.astype('uint8')  # Converte o resultado para tipo uint8
      result = cv2.cvtColor(result, cv2.COLOR_LAB2RGB)  # Converte para RGB

      # Mostra imagem de resultado na tela
      showResult(result, display)

      # Avisa que o processo terminou
      messagebox.showinfo("Process", "The color transfer process was successful!")

   else:
      messagebox.showerror("Unfound file", "You must select source and target images.")
      
# ------------------------------------------------------------------------------------
# Root Window Destruction ------------------------------------------------------------

# Destrói a janela raiz quando uma janela de mais alto nível é destruída
def on_toplevel_close():
    source_window.destroy()

# ------------------------------------------------------------------------------------
# Open File --------------------------------------------------------------------------

# Função que abre arquivo de imagem a partir de um seletor de arquivos
def OpenFile(display, grayscale):
  "Open an image"
  try:
    # Abre o seletor de arquivos
    file = filedialog.askopenfilename(initialdir= "", filetypes= [("Image file", (".png", ".jpg"))])
    # Verifica se o arquivo foi selecionado corretamente
    if file:
        # Lê o arquivo
        img = cv2.imread(file)
        if grayscale:
            # Caso for a imagem target, a mesma deve estar em tons de cinza
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Salva a imagem target na variável
            global target
            target = img
        else:
            # Caso contrário, é source, e a convertemos para o espaço de cores RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # Salva a imagem source na variável
            global source
            source = img
        
        # Configura a imagem e o display indicado para mostra-la na tela.
        img = Image.fromarray(img)
        img = ImageTk.PhotoImage(img)
        display.config(image=img)
        display.image = img
        return file

  except FileNotFoundError:
    messagebox.showerror("Unfound file", "The selected file was not found.")

# ------------------------------------------------------------------------------------
# Open Settings ----------------------------------------------------------------------

# Função que abre janela de configurações
def openSettings():
    global settings_window  # Para rastrear a janela de configurações

    # Verifica se a janela de configurações já está aberta
    if 'settings_window' in globals() and settings_window.winfo_exists():
        settings_window.lift()  # Traz a janela existente para frente
        return

    def saveSettings():
        try:
            global NEIGHBOURHOOD_KERNEL_SIZE, JITTER_SAMPLES, JITTER_SAMPLES_M, JITTER_SAMPLES_N
            # Obtém os novos valores das entradas e atualiza as constantes
            NEIGHBOURHOOD_KERNEL_SIZE = int(kernel_size_entry.get())
            # JITTER_SAMPLES = int(jitter_samples_entry.get())
            JITTER_SAMPLES_M = int(jitter_samples_m_entry.get())
            JITTER_SAMPLES_N = int(jitter_samples_n_entry.get())

            # Fecha a janela de configurações
            settings_window.destroy()
            messagebox.showinfo("Settings", "Settings were saved successfully!")

        except ValueError:
            messagebox.showerror("Error", "Please enter valid values.")

    # Cria uma nova janela para configurações
    settings_window = tk.Toplevel(source_window)
    settings_window.title("Settings")
    settings_window.geometry("+1000+50")

    # Adiciona entradas para cada constante
    tk.Label(settings_window, text="Neighbourhood size:").grid(row=0, column=0, padx=10, pady=5)
    kernel_size_entry = tk.Entry(settings_window)
    kernel_size_entry.insert(0, str(NEIGHBOURHOOD_KERNEL_SIZE))
    kernel_size_entry.grid(row=0, column=1, padx=10, pady=5)

    # tk.Label(settings_window, text="Jitter Samples:").grid(row=1, column=0, padx=10, pady=5)
    # jitter_samples_entry = tk.Entry(settings_window)
    # jitter_samples_entry.insert(0, str(JITTER_SAMPLES))
    # jitter_samples_entry.grid(row=1, column=1, padx=10, pady=5)

    tk.Label(settings_window, text="Jitter M:").grid(row=2, column=0, padx=10, pady=5)
    jitter_samples_m_entry = tk.Entry(settings_window)
    jitter_samples_m_entry.insert(0, str(JITTER_SAMPLES_M))
    jitter_samples_m_entry.grid(row=2, column=1, padx=10, pady=5)

    tk.Label(settings_window, text="Jitter N:").grid(row=3, column=0, padx=10, pady=5)
    jitter_samples_n_entry = tk.Entry(settings_window)
    jitter_samples_n_entry.insert(0, str(JITTER_SAMPLES_N))
    jitter_samples_n_entry.grid(row=3, column=1, padx=10, pady=5)

    # Botão para salvar as configurações
    tk.Button(settings_window, text="Salvar", command=saveSettings).grid(row=4, column=0, columnspan=2, pady=10)

# ------------------------------------------------------------------------------------
# Save Image -------------------------------------------------------------------------

# Função para salvar a imagem gerada
def saveImage(display):
    global result
    if result is not None:
        try:
            # Pega a imagem atualmente exibida no display
            image = display.image._PhotoImage__photo  # Acessa o objeto interno da imagem
            if image:
                # Abre a janela de diálogo para salvar o arquivo
                file_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                        filetypes=[("PNG files", "*.png"),
                                                                    ("JPEG files", "*.jpg"),
                                                                    ("All files", "*.*")])
                if file_path:
                    # Salva a imagem no local especificado
                    image.write(file_path, format="png")
                    messagebox.showinfo("Save Image", "Image saved successfully!")
            else:
                messagebox.showerror("Error", "No image to save.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {e}")

# ------------------------------------------------------------------------------------
# Interface --------------------------------------------------------------------------
# ------------------------------------------------------------------------------------

# Janela Source ----------------------------------------------------------------------

# Janela referente à imagem source
source_window = Tk()
source_window.title('Source Image (Colorful)')

# Define tamanho e posição da janela
source_window.geometry("+0+0")

# Barra de menu da janela source
source_menu_bar = Menu(source_window)

# Display da imagem (começa com imagem default)
source_display = tk.Label(source_window)
source_display.pack()
setDefaultImg(source_display)

# Configura as opções da barra de menu
source_file_menu = Menu(source_menu_bar, tearoff= 0)
source_file_menu.add_command(label= "Import", command = lambda: OpenFile(source_display, 0))
source_menu_bar.add_cascade(label= "File", menu = source_file_menu)
source_window.config(menu = source_menu_bar)

# Janela Target ----------------------------------------------------------------------

# Janela referente à imagem target
target_window = tk.Toplevel(source_window)
target_window.title('Target Image (Grayscale)')

# Define tamanho e posição da janela
target_window.geometry("+500+0")

# Barra de menu da janela target
target_menu_bar = Menu(target_window)

# Display da imagem (começa com imagem default)
target_display = tk.Label(target_window)
target_display.pack()
setDefaultImg(target_display)

# Configura as opções da barra de menu
target_file_menu = Menu(target_menu_bar, tearoff= 0)
target_file_menu.add_command(label= "Import", command = lambda: OpenFile(target_display, 1))
target_menu_bar.add_cascade(label= "File", menu = target_file_menu)
target_window.config(menu = target_menu_bar)

target_window.protocol("WM_DELETE_WINDOW", on_toplevel_close)

# Janela Result ----------------------------------------------------------------------

# Janela referente à imagem result
result_window = tk.Toplevel(source_window)
result_window.title('Result Image (From Color Transfering Process)')

# Define tamanho e posição da janela
result_window.geometry("+1000+0")

# Barra de menu da janela result
result_menu_bar = Menu(result_window)

# Display da imagem (começa com imagem default)
result_display = tk.Label(result_window)
result_display.pack()
setDefaultImg(result_display)

# Configura as opções da barra de menu
result_apply_menu = Menu(result_menu_bar, tearoff= 0)
result_save_menu = Menu(result_menu_bar, tearoff=0)
result_save_menu.add_command(label="Save", command=lambda: saveImage(result_display))
result_menu_bar.add_cascade(label="File", menu=result_save_menu)
result_apply_menu.add_command(label= "Apply", command = lambda: colorTransfer(result_display))
result_menu_bar.add_cascade(label= "Process", menu = result_apply_menu)
result_window.config(menu = result_menu_bar)

result_window.protocol("WM_DELETE_WINDOW", on_toplevel_close)

# ------------------------------------------------------------------------------------

# Adiciona um botão na janela principal para abrir as configurações
result_menu_bar.add_command(label="Settings", command=openSettings)

# ------------------------------------------------------------------------------------

# Mantém o loop da janela principal
source_window.mainloop()