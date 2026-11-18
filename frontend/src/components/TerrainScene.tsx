import { Canvas, useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import type { Mesh, MeshBasicMaterial } from 'three'
import { barHeight, bandColor, isStrong } from '../lib/hud'

export interface TerrainBar {
  symbol: string
  score: number
  band: string
}

interface Props {
  bars: TerrainBar[]
  selected: string | null
  pulsing: Set<string>
  animate: boolean
}

const SPACING = 1.25
const PULSE_SECONDS = 6 // a band flip pings a few times, then settles
const CYAN = '#2de1fc'

function Building({ bar, x, selected, pulse, animate }: { bar: TerrainBar; x: number; selected: boolean; pulse: boolean; animate: boolean }) {
  const ring = useRef<Mesh>(null)
  const startedAt = useRef<number | null>(null)
  const h = barHeight(bar.score)
  const color = bandColor(bar.band)

  useFrame(({ clock }) => {
    const mesh = ring.current
    if (!mesh) return
    if (!pulse) {
      startedAt.current = null
      return
    }
    if (!animate) return
    startedAt.current ??= clock.elapsedTime
    const elapsed = clock.elapsedTime - startedAt.current
    mesh.visible = elapsed < PULSE_SECONDS
    const phase = (elapsed % 2) / 2
    mesh.scale.setScalar(1 + phase * 1.6)
    ;(mesh.material as MeshBasicMaterial).opacity = 1 - phase
  })

  return (
    <group position={[x, 0, 0]}>
      <mesh position={[0, h / 2, 0]}>
        <boxGeometry args={[0.75, h, 0.75]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={isStrong(bar.band) ? 0.9 : 0.4} roughness={0.5} />
      </mesh>
      {selected && (
        <mesh position={[0, h / 2, 0]}>
          <boxGeometry args={[0.9, h + 0.14, 0.9]} />
          <meshBasicMaterial color={CYAN} wireframe />
        </mesh>
      )}
      {pulse && (
        <mesh ref={ring} rotation-x={-Math.PI / 2} position-y={0.03}>
          <ringGeometry args={[0.65, 0.78, 48]} />
          <meshBasicMaterial color={CYAN} transparent />
        </mesh>
      )}
    </group>
  )
}

function Rig({ animate }: { animate: boolean }) {
  useFrame(({ clock, camera }) => {
    camera.position.x = animate ? Math.sin(clock.elapsedTime * 0.2) * 1.6 : 0
    camera.lookAt(0, 1.5, 0)
  })
  return null
}

export default function TerrainScene({ bars, selected, pulsing, animate }: Props) {
  return (
    <Canvas camera={{ position: [0, 3.4, 9.5], fov: 40 }} dpr={[1, 2]} frameloop={animate ? 'always' : 'demand'}>
      <color attach="background" args={['#0a0e14']} />
      <fog attach="fog" args={['#0a0e14', 10, 26]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 8, 6]} intensity={1.1} />
      <pointLight position={[0, 4, 4]} color={CYAN} intensity={12} distance={16} />
      <gridHelper args={[32, 32, '#164b63', '#10202c']} />
      <Rig animate={animate} />
      {bars.map((bar, i) => (
        <Building
          key={bar.symbol}
          bar={bar}
          x={(i - (bars.length - 1) / 2) * SPACING}
          selected={bar.symbol === selected}
          pulse={pulsing.has(bar.symbol)}
          animate={animate}
        />
      ))}
    </Canvas>
  )
}
