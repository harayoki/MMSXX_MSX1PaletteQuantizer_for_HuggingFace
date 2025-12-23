<script lang="ts">
  import { onDestroy } from 'svelte';

  type UploadedImage = {
    id: string;
    name: string;
    size: number;
    type: string;
    url: string;
  };

  let uploadedImages: UploadedImage[] = [];
  let selectedId: string | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let animationSeed = 0;

  const effectSettings = {
    intensity: 0.55,
    grain: 0.25,
    tint: '#7c3aed'
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const withAlpha = (hex: string, alpha: number) => {
    const normalized = hex.replace('#', '');
    const full = normalized.length === 3 ? normalized.split('').map((c) => c + c).join('') : normalized.padEnd(6, '0');
    const num = parseInt(full, 16);
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };

  const handleFileInput = (event: Event) => {
    const files = (event.target as HTMLInputElement).files;
    addFiles(files);
    (event.target as HTMLInputElement).value = '';
  };

  const addFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const nextImages: UploadedImage[] = [];
    Array.from(files).forEach((file) => {
      const url = URL.createObjectURL(file);
      nextImages.push({
        id: crypto.randomUUID(),
        name: file.name,
        size: file.size,
        type: file.type,
        url
      });
    });
    uploadedImages = [...uploadedImages, ...nextImages];
    if (!selectedId && nextImages.length) {
      selectedId = nextImages[0].id;
    }
  };

  const handleDrop = (event: DragEvent) => {
    event.preventDefault();
    addFiles(event.dataTransfer?.files ?? null);
  };

  const selectedImage = () => uploadedImages.find((image) => image.id === selectedId);

  const drawPreview = () => {
    const current = selectedImage();
    if (!canvas || !current) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      const maxWidth = 1024;
      const scale = Math.min(1, maxWidth / img.width);
      const width = Math.max(1, Math.round(img.width * scale));
      const height = Math.max(1, Math.round(img.height * scale));

      canvas.width = width;
      canvas.height = height;

      ctx.clearRect(0, 0, width, height);
      ctx.save();
      ctx.filter = `saturate(${1 + effectSettings.intensity * 0.8}) brightness(${1 + effectSettings.intensity * 0.25}) contrast(${1 + effectSettings.intensity * 0.35})`;
      ctx.drawImage(img, 0, 0, width, height);
      ctx.restore();

      applyDummyEffect(ctx, width, height);
    };
    img.src = current.url;
  };

  const applyDummyEffect = (ctx: CanvasRenderingContext2D, width: number, height: number) => {
    ctx.save();
    ctx.globalCompositeOperation = 'soft-light';
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, withAlpha(effectSettings.tint, 0.12 + effectSettings.intensity * 0.25));
    gradient.addColorStop(1, withAlpha('#0ea5e9', 0.1 + effectSettings.grain * 0.3));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    const stripeGap = Math.max(16, 38 - Math.round(effectSettings.intensity * 18));
    ctx.globalAlpha = 0.14 + effectSettings.intensity * 0.2;
    ctx.globalCompositeOperation = 'overlay';
    ctx.fillStyle = withAlpha('#ffffff', 0.08 + effectSettings.grain * 0.12);
    for (let x = -height; x < width + height; x += stripeGap) {
      ctx.save();
      ctx.translate(x, 0);
      ctx.rotate(-Math.PI / 4);
      ctx.fillRect(0, 0, height * 2, stripeGap / 2.2);
      ctx.restore();
    }

    ctx.globalCompositeOperation = 'screen';
    ctx.globalAlpha = 0.35 * (0.4 + effectSettings.grain);
    const sparkCount = Math.min(1400, Math.round((width + height) * 0.2 * (0.6 + effectSettings.grain)));
    for (let i = 0; i < sparkCount; i++) {
      const x = Math.abs(Math.sin(i * 12.9898 + animationSeed * 1.7) * 43758.5453) % width;
      const y = Math.abs(Math.cos(i * 78.233 + animationSeed * 0.9) * 12345.6789) % height;
      const size = 1 + effectSettings.intensity * 2;
      ctx.fillStyle = withAlpha('#38bdf8', 0.12 + effectSettings.grain * 0.18);
      ctx.fillRect(x, y, size, size);
    }

    ctx.globalCompositeOperation = 'source-over';
    ctx.restore();
  };

  const downloadPreview = async () => {
    if (!canvas || !selectedImage()) return;
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${selectedImage()?.name ?? 'preview'}.png`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const downloadOriginal = () => {
    const current = selectedImage();
    if (!current) return;
    const link = document.createElement('a');
    link.href = current.url;
    link.download = current.name;
    link.click();
  };

  const refreshDummyEffect = () => {
    animationSeed += 1;
    drawPreview();
  };

  const removeAll = () => {
    uploadedImages.forEach((image) => URL.revokeObjectURL(image.url));
    uploadedImages = [];
    selectedId = null;
    if (canvas) {
      canvas.width = canvas.height = 0;
    }
  };

  $: {
    selectedId;
    effectSettings.intensity;
    effectSettings.grain;
    effectSettings.tint;
    animationSeed;
    drawPreview();
  }

  onDestroy(() => {
    uploadedImages.forEach((image) => URL.revokeObjectURL(image.url));
  });
</script>

<main>
  <h1>MSX1 Palette Quantizer (SvelteKit)</h1>
  <p class="lead">
    画像のアップロード／ダウンロードはこれまで通り。エフェクト処理は準備中のため、キャンバスでダミーのプレビューを即時更新します。
  </p>

  <div class="grid">
    <section class="upload-box" on:drop={handleDrop} on:dragover|preventDefault on:dragenter|preventDefault>
      <div class="dropzone">
        <label for="file-input">画像をアップロード</label>
        <input id="file-input" type="file" accept="image/*" multiple on:change={handleFileInput} />
        <p class="muted">PNGやJPEGをまとめてドロップ／選択できます。選択後は左のカードからプレビュー対象を切り替えられます。</p>
        {#if uploadedImages.length}
          <button class="secondary" type="button" on:click={removeAll}>リセット</button>
        {/if}
      </div>

      {#if uploadedImages.length}
        <div class="file-list">
          {#each uploadedImages as image}
            <article class={`file-card ${selectedId === image.id ? 'active' : ''}`} on:click={() => (selectedId = image.id)}>
              <img class="thumb" alt={image.name} src={image.url} loading="lazy" />
              <div class="file-meta">
                <strong>{image.name}</strong>
                <span class="muted">{formatSize(image.size)} ・ {image.type || 'image'}</span>
                {#if selectedId === image.id}
                  <span class="muted">プレビュー中</span>
                {/if}
              </div>
            </article>
          {/each}
        </div>
      {:else}
        <p class="muted">まだアップロードされた画像がありません。</p>
      {/if}
    </section>

    <section class="controls">
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem;">
        <div class="control">
          <label for="intensity">エフェクト強度</label>
          <input
            id="intensity"
            type="range"
            min="0"
            max="1"
            step="0.01"
            bind:value={effectSettings.intensity}
          />
          <span class="control-value">{Math.round(effectSettings.intensity * 100)}%</span>
        </div>
        <div class="control">
          <label for="grain">グレイン／ちらつき</label>
          <input id="grain" type="range" min="0" max="1" step="0.01" bind:value={effectSettings.grain} />
          <span class="control-value">{Math.round(effectSettings.grain * 100)}%</span>
        </div>
        <div class="control">
          <label for="tint">カラーアクセント</label>
          <input id="tint" type="color" bind:value={effectSettings.tint} />
          <span class="control-value">{effectSettings.tint}</span>
        </div>
      </div>

      <div class="actions">
        <button class="primary" type="button" disabled={!selectedId} on:click={refreshDummyEffect}>
          ダミーエフェクトを更新
        </button>
        <button class="secondary" type="button" disabled={!selectedId} on:click={downloadPreview}>
          プレビューをダウンロード
        </button>
        <button class="secondary" type="button" disabled={!selectedId} on:click={downloadOriginal}>
          元画像をダウンロード
        </button>
      </div>

      <div class="canvas-shell">
        <canvas bind:this={canvas}></canvas>
        <p class="muted">
          {#if selectedId}
            ダミーのエフェクトを重ねた結果をキャンバスに表示しています。スライダーやボタンを動かして挙動を確認してください。
          {:else}
            画像を選択するとここにプレビューが描画されます。
          {/if}
        </p>
      </div>
    </section>
  </div>
</main>
