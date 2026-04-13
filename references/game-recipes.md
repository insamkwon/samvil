# Game Recipes — Phaser 3 + Vite + TypeScript

Common patterns for building Phaser 3 games in SAMVIL.

## 1. Project Setup

### Phaser 3 + Vite + TypeScript

```bash
npm create vite@5.4.21 my-game -- --template vanilla-ts
cd my-game && npm install && npm install phaser@3.87.0
```

### Directory Structure

```
my-game/
  public/
    assets/
      sprites/     # Sprite images (if any)
      images/      # Background images
      audio/       # Sound effects, music
  src/
    main.ts        # Phaser game config + boot
    config/
      game-config.ts  # Game constants (dimensions, physics, colors)
    scenes/
      BootScene.ts    # Asset preloading
      MenuScene.ts    # Start / restart screen
      GameScene.ts    # Main gameplay
      GameOverScene.ts # Score display + restart
    entities/
      Player.ts       # Player entity
      Enemy.ts        # Enemy entity
      Collectible.ts  # Collectible items
  index.html           # Vite entry point
  package.json
  tsconfig.json
  vite.config.ts
```

### Phaser Config (src/main.ts)

```typescript
import Phaser from "phaser";
import { BootScene } from "./scenes/BootScene";
import { MenuScene } from "./scenes/MenuScene";
import { GameScene } from "./scenes/GameScene";
import { GameOverScene } from "./scenes/GameOverScene";
import { GAME_CONFIG } from "./config/game-config";

const config: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  width: GAME_CONFIG.width,
  height: GAME_CONFIG.height,
  physics: {
    default: "arcade",
    arcade: {
      gravity: { x: 0, y: 0 },
      debug: false,
    },
  },
  scene: [BootScene, MenuScene, GameScene, GameOverScene],
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
};

new Phaser.Game(config);
```

## 2. Scene Lifecycle

Every Phaser scene follows: `preload()` -> `create()` -> `update()`

```typescript
import Phaser from "phaser";

export class MyScene extends Phaser.Scene {
  constructor() {
    super({ key: "MyScene" });
  }

  // Called once — load external assets here
  preload(): void {
    this.load.image("player", "assets/sprites/player.png");
    this.load.audio("jump", "assets/audio/jump.mp3");
  }

  // Called once after preload — set up game objects
  create(): void {
    this.cameras.main.setBackgroundColor("#1a1a2e");
    const player = this.physics.add.sprite(400, 300, "player");
    this.physics.add.collider(player, platforms);
  }

  // Called every frame (~60fps) — game loop
  update(time: number, delta: number): void {
    // Check input, move entities, update game state
    if (this.cursors.left.isDown) {
      this.player.setVelocityX(-200);
    }
  }
}
```

### Scene Transitions

```typescript
// Start another scene (replaces current)
this.scene.start("GameOverScene", { score: this.score });

// Pause current scene and launch another on top
this.scene.launch("PauseMenuScene");

// Resume a paused scene
this.scene.resume("GameScene");

// Stop a scene
this.scene.stop("GameScene");
```

## 3. Arcade Physics

### Basic Physics Setup

```typescript
// Enable physics on a sprite
const player = this.physics.add.sprite(x, y, "player");

// Set physics properties
player.setCollideWorldBounds(true);
player.setBounce(0.2);
player.setGravityY(300);

// Velocity-based movement
player.setVelocityX(200);
player.setVelocityY(-400); // Jump
```

### Collision Detection

```typescript
// Both objects bounce off each other
this.physics.add.collider(player, platforms);

// Trigger callback when objects overlap (no physics response)
this.physics.add.overlap(player, collectibles, (player, collectible) => {
  collectible.destroy();
  this.score += 10;
  this.scoreText.setText("Score: " + this.score);
});

// Collision with callback
this.physics.add.collider(player, enemies, (player, enemy) => {
  this.scene.start("GameOverScene", { score: this.score });
});
```

### Physics Groups

```typescript
// Create a static group (platforms, walls)
const platforms = this.physics.add.staticGroup();
platforms.create(400, 568, "ground").setScale(2).refreshBody();

// Create a dynamic group (enemies, collectibles)
const enemies = this.physics.add.group({
  key: "enemy",
  repeat: 5,
  setXY: { x: 100, y: 0, stepX: 120 },
});

enemies.children.iterate((child) => {
  child.setBounceY(Phaser.Math.FloatBetween(0.4, 0.8));
  child.setCollideWorldBounds(true);
});
```

## 4. Input Handling

### Keyboard Input

```typescript
// Cursor keys (arrow keys)
const cursors = this.input.keyboard!.createCursorKeys();

// In update():
if (cursors.left.isDown) {
  player.setVelocityX(-160);
} else if (cursors.right.isDown) {
  player.setVelocityX(160);
} else {
  player.setVelocityX(0);
}

if (cursors.up.isDown && player.body!.touching.down) {
  player.setVelocityY(-330); // Jump
}

// Specific keys
const spaceKey = this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE);
if (Phaser.Input.Keyboard.JustDown(spaceKey)) {
  this.fireBullet();
}

// WASD
const wasd = this.input.keyboard!.addKeys({
  up: Phaser.Input.Keyboard.KeyCodes.W,
  down: Phaser.Input.Keyboard.KeyCodes.S,
  left: Phaser.Input.Keyboard.KeyCodes.A,
  right: Phaser.Input.Keyboard.KeyCodes.D,
});
```

### Mouse / Touch Input

```typescript
// Click/tap anywhere
this.input.on("pointerdown", (pointer: Phaser.Input.Pointer) => {
  const worldPoint = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
  player.moveTo(worldPoint.x, worldPoint.y);
});

// Click/tap on a specific game object
player.setInteractive();
this.input.on("gameobjectdown", (pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject) => {
  gameObject.destroy();
});

// Drag
player.setInteractive({ draggable: true });
this.input.on("drag", (pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject, dragX: number, dragY: number) => {
  gameObject.x = dragX;
  gameObject.y = dragY;
});

// Touch-friendly buttons for mobile
const jumpButton = this.add.text(700, 500, "JUMP", { fontSize: "24px" })
  .setInteractive()
  .on("pointerdown", () => player.setVelocityY(-330));
```

## 5. Score / State Management

### Score Display

```typescript
// Create score text
private score = 0;
private scoreText!: Phaser.GameObjects.Text;

create(): void {
  this.scoreText = this.add.text(16, 16, "Score: 0", {
    fontSize: "24px",
    color: "#ffffff",
    fontFamily: "monospace",
  });
}

addScore(points: number): void {
  this.score += points;
  this.scoreText.setText("Score: " + this.score);
}
```

### Timer

```typescript
private timer!: Phaser.Time.TimerEvent;
private timeLeft = 60;

create(): void {
  this.timer = this.time.addEvent({
    delay: 1000, // 1 second
    callback: () => {
      this.timeLeft--;
      this.timerText.setText("Time: " + this.timeLeft);
      if (this.timeLeft <= 0) {
        this.gameOver();
      }
    },
    loop: true,
  });
}
```

### Game State Reset (for restart)

```typescript
// In GameScene
create(): void {
  // Reset all state
  this.score = 0;
  this.timeLeft = 60;
  this.isGameOver = false;
  this.scoreText.setText("Score: 0");
  // Re-create entities...
}
```

## 6. Asset Loading

### Code-Generated Graphics (no external files)

```typescript
// Player as a colored rectangle
const graphics = this.add.graphics();
graphics.fillStyle(0x00ff88);
graphics.fillRoundedRect(-16, -16, 32, 32, 4);
graphics.generateTexture("player", 32, 32);
graphics.destroy();

// Now use as sprite
const player = this.physics.add.sprite(400, 300, "player");
```

### Loading External Assets

```typescript
// In BootScene.preload():
preload(): void {
  // Progress bar
  const bar = this.add.graphics();
  this.load.on("progress", (value: number) => {
    bar.clear();
    bar.fillStyle(0x00ff88);
    bar.fillRect(100, 280, 600 * value, 40);
  });

  // Images
  this.load.image("sky", "assets/images/sky.png");
  this.load.image("ground", "assets/images/ground.png");

  // Sprite sheets
  this.load.spritesheet("dude", "assets/sprites/dude.png", {
    frameWidth: 32,
    frameHeight: 48,
  });

  // Audio
  this.load.audio("jump", ["assets/audio/jump.mp3"]);
  this.load.audio("bgm", ["assets/audio/bgm.mp3"]);
}

create(): void {
  this.scene.start("MenuScene");
}
```

### Playing Audio

```typescript
// Sound effect
this.sound.play("jump");

// Background music (looped)
const bgm = this.sound.add("bgm", { loop: true, volume: 0.5 });
bgm.play();
```

## 7. Game Config Patterns

### game-config.ts

```typescript
export const GAME_CONFIG = {
  // Dimensions
  width: 800,
  height: 600,

  // Physics
  physics: "arcade" as const,
  gravity: { x: 0, y: 0 }, // Set y: 300 for platformer

  // Input
  input: "keyboard" as const, // "keyboard" | "mouse" | "touch"

  // Gameplay
  playerSpeed: 200,
  jumpForce: 400,
  enemySpeed: 100,
  collectibleScore: 10,
} as const;

export const COLORS = {
  bg: 0x1a1a2e,
  player: 0x00ff88,
  enemy: 0xff4444,
  collectible: 0xffdd44,
  platform: 0x4a4a6a,
  text: 0xffffff,
} as const;
```

### Platformer Config

```typescript
export const GAME_CONFIG = {
  width: 800,
  height: 600,
  physics: "arcade",
  gravity: { x: 0, y: 500 }, // Gravity pulls down
  input: "keyboard",
  playerSpeed: 160,
  jumpForce: 400,
};
```

### Top-Down Config

```typescript
export const GAME_CONFIG = {
  width: 800,
  height: 600,
  physics: "arcade",
  gravity: { x: 0, y: 0 }, // No gravity
  input: "keyboard",
  playerSpeed: 200,
};
```

### Touch/Mobile Config

```typescript
export const GAME_CONFIG = {
  width: 375,
  height: 667,
  physics: "arcade",
  gravity: { x: 0, y: 0 },
  input: "touch",
  playerSpeed: 150,
};
```
