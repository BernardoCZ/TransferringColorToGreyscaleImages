# ------------------------------------------------------------------------------------
# Bibliotecas ------------------------------------------------------------------------

import numpy as np
from scipy.ndimage import generic_filter
import cv2
import random

import tkinter as tk
from tkinter import *
from tkinter import filedialog, messagebox
from tkinter.simpledialog import askinteger
from PIL import Image, ImageTk

# ------------------------------------------------------------------------------------
# Constantes -------------------------------------------------------------------------

# Tamanho da vizinhança em que se pré-computa o desvio padrão no processo de transferência de cores
NEIGHBOURHOOD_KERNEL_SIZE = 5

# Constantes do processo de jitter sampling
JITTER_SAMPLES = 50
JITTER_SAMPLES_M = int(np.ceil(np.sqrt(JITTER_SAMPLES)))
JITTER_SAMPLES_N = JITTER_SAMPLES_M

# Constantes relativas aos swatches
MAX_SWATCHES = 10
SWATCH_COLORS = ["red", "blue", "green", "yellow", "purple", "pink", "cyan", "orange", "black", "grey"]
SWATCH_DEFAULT_WIDTH = 50
SWATCH_DEFAULT_HEIGHT = 50

# Constantes relativas ao texture synthesis
WINDOW_SIZE = 5  # Tamanho da janela de vizinhança para síntese de textura

# ------------------------------------------------------------------------------------
# Definição das imagens envolvidas no processo de transferência de cores
source = None
target = None
result = None

# Definição dos swatches nas imagens
swatches = []

# ------------------------------------------------------------------------------------
# Set Default Image ------------------------------------------------------------------

# Função que coloca a imagem default no display informado
def setDefaultImg(display):
    default = ImageTk.PhotoImage(file="img/default.jpg")
    display.config(image=default)
    display.image = default

# ------------------------------------------------------------------------------------
# Add Swatch -------------------------------------------------------------------------

# Função que adiciona um swatch na lista de swatches selecionados.
def add_swatch(event, image_type):
    global swatches

    # Verifica o número de swatches para cada imagem
    source_count = len([s for s in swatches if s["type"] == "source"])
    target_count = len([s for s in swatches if s["type"] == "target"])

    if image_type == "source" and source_count >= MAX_SWATCHES:
        messagebox.showerror("Limite atingido", f"Você pode selecionar até {MAX_SWATCHES} swatches para a imagem source.")
        return
    elif image_type == "target" and target_count >= MAX_SWATCHES:
        messagebox.showerror("Limite atingido", f"Você pode selecionar até {MAX_SWATCHES} swatches para a imagem target.")
        return

    # Determina as dimensões do swatch
    if image_type == "source" and source is not None:
        img_width, img_height = source.shape[1], source.shape[0]
    elif image_type == "target" and target is not None:
        img_width, img_height = target.shape[1], target.shape[0]
    else:
        return

    # Solicita a largura e altura ao usuário
    width = askinteger("Largura do Swatch", "Insira a largura do swatch (px):", minvalue=1, maxvalue=img_width, initialvalue=SWATCH_DEFAULT_WIDTH, parent=source_window if image_type == "source" else target_window)
    if width:
        height = askinteger("Altura do Swatch", "Insira a altura do swatch (px):", minvalue=1, maxvalue=img_height, initialvalue=SWATCH_DEFAULT_HEIGHT, parent=source_window if image_type == "source" else target_window)

    if not width or not height:
        return

    # Determina as coordenadas do retângulo, respeitando os limites da imagem
    x1, y1 = event.x, event.y
    x2, y2 = min(x1 + width, img_width), min(y1 + height, img_height)

    # Determina a cor para o novo swatch
    swatch_index = min(source_count, target_count)
    color = SWATCH_COLORS[swatch_index]

    # Adiciona o swatch
    swatches.append({
        "type": image_type,
        "coords": (x1, y1, x2, y2),
        "color": color
    })

    # Desenha o retângulo
    display = source_display if image_type == "source" else target_display
    canvas = display.canvas
    canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)

# ------------------------------------------------------------------------------------
# Clear Swatch -----------------------------------------------------------------------

# Função que remove todos os swatches da imagem especificada.
def clear_swatches(image_type):
    global source, target

    if (image_type == "source" and source is not None) or (image_type == "target" and target is not None):
        global swatches
        
        # Filtra os swatches que não correspondem ao tipo especificado
        swatches = [s for s in swatches if s["type"] != image_type]

        # Redesenha o canvas
        if image_type == "source":
            display = source_display
        else:
            display = target_display

        canvas = display.canvas
        canvas.delete("all")
        canvas.create_image(0, 0, anchor=NW, image=display.image)

# ------------------------------------------------------------------------------------
# Configure Canvas -------------------------------------------------------------------

# Função que configura o canvas para ter o mesmo tamanho da imagem e exibir swatches sobrepostos.
def configure_canvas(display, image):

    # Remove o canvas existente, se houver
    if hasattr(display, "canvas") and display.canvas is not None:
        display.canvas.destroy()

    canvas = Canvas(display, width=image.shape[1], height=image.shape[0], bg="white", highlightthickness=0)
    canvas.pack(fill=BOTH, expand=True)
    canvas.create_image(0, 0, anchor=NW, image=display.image)
    return canvas

# ------------------------------------------------------------------------------------
# Configure Canvas Events ------------------------------------------------------------

# Função que configura eventos de clique nos canvas para seleção de swatches.
def configure_canvas_events():
    global source, target
    if source is not None:
        source_display.canvas.bind("<Button-1>", lambda event: add_swatch(event, "source"))
    if target is not None:
        target_display.canvas.bind("<Button-1>", lambda event: add_swatch(event, "target"))

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
# Texture Synthesis ------------------------------------------------------------------
# Função que faz a síntese de texturas dos swatches coloridos para os pixels não coloridos.
def texture_synthesis(colorized_swatches, result_img, result_mask):

    # Aplica padding para evitar problemas em bordas.
    half_size = WINDOW_SIZE // 2
    size = 2*half_size
    result_pad = cv2.copyMakeBorder(result_img, size, size, size, size, cv2.BORDER_REPLICATE)
    mask_pad = cv2.copyMakeBorder(result_mask, size, size, size, size, cv2.BORDER_REPLICATE)
    swatches_pad = {}
    for k in range(len(colorized_swatches)):
        swatches_pad[k] = cv2.copyMakeBorder(colorized_swatches[k], size, size, size, size, cv2.BORDER_REPLICATE)

    # Iterando pelos pixels da imagem de resultado em passos de 2*d
    for i in range(size, result_pad.shape[0]-half_size, size):
        for j in range(size, result_pad.shape[1]-half_size, size):

            # Ignora janelas completamente marcadas
            if all(mask_pad[i+dx, j+dy] == 1 for dx in [-half_size, half_size] for dy in [-half_size, half_size]):
                continue

            # Extraindo janela de vizinhança do canal de luminância (L)
            temp = result_pad[i-half_size:i+half_size, j-half_size:j+half_size, 0]
            min_error = float('inf')  # Inicializando erro mínimo
            best_patch = None

            # Comparando com todos os swatches
            for swatch in swatches_pad.values():
                # Iterando pelas janelas dentro do swatch
                for l in range(size, swatch.shape[0]-half_size, size):
                    for m in range(size, swatch.shape[1]-half_size, size):
                        each = swatch[l-half_size:l+half_size, m-half_size:m+half_size, 0]
                        error = np.sum((temp - each) ** 2)  # Calculando erro

                        # Atualizando a melhor correspondência
                        if error < min_error:
                            min_error = error
                            best_patch = swatch[l-half_size:l+half_size, m-half_size:m+half_size]
            
            # Aplicando a melhor correspondência de cor (A e B)
            if best_patch is not None:
                result_pad[i-half_size:i+half_size, j-half_size:j+half_size, 1:] = best_patch[:, :, 1:]

    # Retorna o resultado sem o padding
    return result_pad[size:-size, size:-size]

# ------------------------------------------------------------------------------------
# Transferring Color to Greyscale Images ---------------------------------------------

# Algoritmo do processo de transferência de cores
def colorTransfer(display):
    global source, target, result
   
    # Verifica se as imagens foram selecionadas
    if source is not None and target is not None:
        global swatches

        # Verifica o número de swatches para cada imagem
        source_count = len([s for s in swatches if s["type"] == "source"])
        target_count = len([s for s in swatches if s["type"] == "target"])
        
        # Verifica se o número de swatches em cada imagem é igual
        if source_count == target_count:

            # Verifica se há pelo menos um swatch
            if source_count != 0:

                # Converte a imagem source para o espaço de cores Lab
                sourceLab = cv2.cvtColor(source, cv2.COLOR_RGB2Lab)
                
                # Converte para tipo float64 para maior precisão
                sourceLab = sourceLab.astype(np.float64)
                targetLum = target.astype(np.float64)
                
                # Pega a luminância da imagem source
                sourceLum = sourceLab[:,:,0]

                # Configura variável que guarda o resultado do processo
                result_aux = np.zeros((targetLum.shape[0], targetLum.shape[1], 3))  # Inicializa o array do resultado
                result_aux[:, :, 0] = targetLum  # Copia o canal de luminância da imagem target

                # Configura variável que guarda quais pixels da imagem de resultado estão coloridos após o processo sobre o par de swatches
                result_colorized_pixels = np.zeros((targetLum.shape[0], targetLum.shape[1]))

                # Configura variável que guarda os swatches do resultado
                result_swatches = {}  # Inicializa o array do resultado

                global SWATCH_COLORS
                source_idx = 0
                target_idx = 0

                # Passa por cada par de swatches
                for i in range(source_count):

                    # Pega o índice dos par de swatches
                    for j in range(source_count*2):
                        if swatches[j]["color"] == SWATCH_COLORS[i]:
                            if swatches[j]["type"] == "source":
                                source_idx = j
                            else:
                                target_idx = j

                    # Pega as coordenadas das imagens capturadas pelo respectivo swatch
                    source_coords = swatches[source_idx]["coords"]
                    target_coords = swatches[target_idx]["coords"]

                    # Pega o pedaço da imagem referente ao respectivo swatch
                    sourceLab_patch = sourceLab[source_coords[1]:source_coords[3], source_coords[0]:source_coords[2]]
                    source_patch = sourceLum[source_coords[1]:source_coords[3], source_coords[0]:source_coords[2]]
                    target_patch = targetLum[target_coords[1]:target_coords[3], target_coords[0]:target_coords[2]]

                    # Realiza o Luminance Remapping sobre a imagem source
                    sourceRemap = lumRemap(source_patch, target_patch)

                    # Pré-computa o desvio padrão dos valores de luminância de vizinhanças 5x5 em cada imagem.
                    sourceStd = generic_filter(sourceRemap, np.std, size = NEIGHBOURHOOD_KERNEL_SIZE)
                    targetStd = generic_filter(target_patch, np.std, size = NEIGHBOURHOOD_KERNEL_SIZE)

                    # Realiza Jitter Sampling para diminuir o número de amostras necessárias da imagem source
                    sourceSamplesCoord, sourceSamplesLum, sourceSamplesStd = jitterSampling(sourceRemap, JITTER_SAMPLES_M, JITTER_SAMPLES_N, sourceStd)

                    # Configura variável que guarda o resultado do processo sobre o par de swatches
                    result_patch = np.zeros((target_patch.shape[0], target_patch.shape[1], 3))  # Inicializa o array do resultado
                    result_patch[:, :, 0] = target_patch  # Copia o canal de luminância da imagem target

                    # Loop para colorir cada pixel da imagem
                    for m in range(result_patch.shape[0]):
                        for n in range(result_patch.shape[1]):
                        
                            # Encontra a melhor cor de match para o pixel, onde a cor é dada pelos índices dos canais alfa e beta da imagem source
                            [a, b] = bestMatch(result_patch[m][n][0], targetStd[m][n], sourceSamplesLum, sourceSamplesCoord, sourceSamplesStd)

                            # Pega os valores dos canais alfa e beta do pixel da imagem original
                            alpha_channel = sourceLab_patch[a][b][1]  # Canal alpha
                            beta_channel = sourceLab_patch[a][b][2]  # Canal beta

                            # Salva os valores dos canais alfa e beta na imagem resultante
                            result_patch[m][n][1] = alpha_channel
                            result_patch[m][n][2] = beta_channel

                    # Salva as novas cores na imagem de resultado
                    result_aux[target_coords[1]:target_coords[3], target_coords[0]:target_coords[2]] = result_patch

                    # Indica que o pixel foi colorido
                    result_colorized_pixels[target_coords[1]:target_coords[3], target_coords[0]:target_coords[2]] = 1

                    # Salva o swatch da imagem de resultado
                    result_swatches[i] = result_patch
                
                # Realiza a síntese de texturas para colorir a imagem
                result = texture_synthesis(result_swatches, result_aux, result_colorized_pixels)
                
                # Configura imagem do resultado
                result = result.astype('uint8')  # Converte o resultado para tipo uint8
                result = cv2.cvtColor(result, cv2.COLOR_LAB2RGB)  # Converte para RGB

                # Mostra imagem de resultado na tela
                showResult(result, display)

                # Avisa que o processo terminou
                messagebox.showinfo("Process", "The color transfer process was successful!")

            else:
                messagebox.showinfo("Error", "At least one swatch must be selected in each image.")
        else:
            messagebox.showinfo("Error", "Number of swatches in source and target images must be equal.")
    else:
        messagebox.showinfo("Unfound file", "You must select source and target images.")
      
# ------------------------------------------------------------------------------------
# Root Window Destruction ------------------------------------------------------------

# Destrói a janela raiz quando uma janela de mais alto nível é destruída
def on_toplevel_close():
    source_window.destroy()

# ------------------------------------------------------------------------------------
# Open File --------------------------------------------------------------------------

# Função que abre arquivo de imagem a partir de um seletor de arquivos
def OpenFile(image_type, display, grayscale):
  "Open an image"
  try:
    # Abre o seletor de arquivos
    file = filedialog.askopenfilename(initialdir= "", filetypes= [("Image file", (".png", ".jpg"))])
    # Verifica se o arquivo foi selecionado corretamente
    if file:

        # Limpa swatches e canvas antigo caso existam
        clear_swatches(image_type)

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
        image = Image.fromarray(img)
        image = ImageTk.PhotoImage(image)
        display.image = image
        display.canvas = configure_canvas(display, img)

        # Configura eventos nos canvas
        configure_canvas_events()

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
            global NEIGHBOURHOOD_KERNEL_SIZE, JITTER_SAMPLES_M, JITTER_SAMPLES_N, WINDOW_SIZE
            # Obtém os novos valores das entradas e atualiza as constantes
            NEIGHBOURHOOD_KERNEL_SIZE = int(kernel_size_entry.get())
            JITTER_SAMPLES_M = int(jitter_samples_m_entry.get())
            JITTER_SAMPLES_N = int(jitter_samples_n_entry.get())
            WINDOW_SIZE = int(window_size_entry.get())

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

    tk.Label(settings_window, text="Jitter M:").grid(row=2, column=0, padx=10, pady=5)
    jitter_samples_m_entry = tk.Entry(settings_window)
    jitter_samples_m_entry.insert(0, str(JITTER_SAMPLES_M))
    jitter_samples_m_entry.grid(row=2, column=1, padx=10, pady=5)

    tk.Label(settings_window, text="Jitter N:").grid(row=3, column=0, padx=10, pady=5)
    jitter_samples_n_entry = tk.Entry(settings_window)
    jitter_samples_n_entry.insert(0, str(JITTER_SAMPLES_N))
    jitter_samples_n_entry.grid(row=3, column=1, padx=10, pady=5)

    tk.Label(settings_window, text="Window Size:").grid(row=4, column=0, padx=10, pady=5)
    window_size_entry = tk.Entry(settings_window)
    window_size_entry.insert(0, str(WINDOW_SIZE))
    window_size_entry.grid(row=4, column=1, padx=10, pady=5)

    # Botão para salvar as configurações
    tk.Button(settings_window, text="Salvar", command=saveSettings).grid(row=5, column=0, columnspan=2, pady=10)

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
source_file_menu.add_command(label= "Import", command = lambda: OpenFile("source", source_display, 0))
source_menu_bar.add_cascade(label= "File", menu = source_file_menu)

source_swatches_menu = Menu(source_menu_bar, tearoff= 0)
source_swatches_menu.add_command(label="Clear", command=lambda: clear_swatches("source"))
source_menu_bar.add_cascade(label= "Swatches", menu = source_swatches_menu)

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
target_file_menu.add_command(label= "Import", command = lambda: OpenFile("target", target_display, 1))
target_menu_bar.add_cascade(label= "File", menu = target_file_menu)

target_swatches_menu = Menu(target_menu_bar, tearoff= 0)
target_swatches_menu.add_command(label="Clear", command=lambda: clear_swatches("target"))
target_menu_bar.add_cascade(label= "Swatches", menu = target_swatches_menu)

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