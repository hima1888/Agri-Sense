/**
 * The 3D digital twin. Every object is driven by the /twin API response (plus live SSE
 * readings); objects the API marks `schematic` are drawn the same way but labelled as
 * schematic in the UI. No geometry or values are invented here.
 */
import { OrbitControls, Sky, Stars } from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef, type ComponentRef, type ReactNode } from 'react'
import * as THREE from 'three'
import { clientRectEvents } from './events'
import {
  bbox,
  canopySize,
  canopyTint,
  cropInstances,
  cropRows,
  frameDistance,
  hash01,
  healthStyle,
  moistureColor,
  sensorStatus,
  sunDirection,
  type RowSegment,
  type XZ,
} from './layout'
import type { FarmTwin, Infra, InfraOf, Layers, Selection, TwinSensor, TwinZone } from './schemas'

const SOIL = '#5a4331'
const SOIL_DRY = '#6e5640'
const GRASS = '#3f5a33'
const ROAD = '#7a6f5c'
const WATER = '#3b82a0'
const SELECT = '#e2cf98'

export interface SceneProps {
  twin: FarmTwin
  sensors: TwinSensor[] // API sensors with live values merged in
  layers: Layers
  selection: Selection
  onSelect: (s: Selection) => void
  reducedMotion: boolean
  resetSignal: number
  now: number
}

export function TwinCanvas(props: SceneProps) {
  const { min, max } = props.twin.extent
  const dist = frameDistance(props.twin.extent)
  const cx = (min[0] + max[0]) / 2
  const cz = (min[1] + max[1]) / 2
  // Stable identity: a new array on every render would re-run the camera reset effect on
  // every live reading and snap the user's view back.
  const center = useMemo<XZ>(() => [cx, cz], [cx, cz])
  return (
    <Canvas
      shadows
      events={clientRectEvents}
      dpr={[1, 1.75]}
      frameloop={props.reducedMotion ? 'demand' : 'always'}
      camera={{ position: [cx + dist * 0.55, dist * 0.55, cz + dist * 0.75], fov: 42, near: 1, far: dist * 12 }}
      onPointerMissed={() => props.onSelect(null)}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      onCreated={({ gl, scene, camera }) => {
        gl.toneMapping = THREE.ACESFilmicToneMapping
        // Development-only inspection hook (stripped from production builds).
        if (import.meta.env.DEV) (window as unknown as Record<string, unknown>).__AGRI_TWIN__ = { gl, scene, camera }
      }}
      aria-label={`3D model of ${props.twin.farm_name}`}
    >
      <SceneContents {...props} center={center} dist={dist} />
    </Canvas>
  )
}

function SceneContents({
  twin,
  sensors,
  layers,
  selection,
  onSelect,
  reducedMotion,
  resetSignal,
  now,
  center,
  dist,
}: SceneProps & { center: XZ; dist: number }) {
  const sun = twin.sun
  const night = !sun || sun.elevation_deg < -2
  const sunDir = useMemo(
    () => (sun ? sunDirection(Math.max(sun.elevation_deg, -10), sun.azimuth_deg) : ([0.3, 0.5, -0.4] as const)),
    [sun],
  )
  const daylight = sun ? THREE.MathUtils.clamp((sun.elevation_deg + 4) / 30, 0, 1) : 0.3
  const cloud = (twin.weather?.cloud_cover_pct ?? 30) / 100
  const wind = twin.weather?.wind_speed_ms ?? 1.5
  const raining = (twin.weather?.precipitation_mm ?? 0) > 0

  const selectedZone = selection?.kind === 'zone' ? selection.id : null
  const selectedSensor = selection?.kind === 'sensor' ? selection.id : null
  const selectedInfra = selection?.kind === 'infra' ? selection.id : null

  const focus = useMemo((): [number, number, number] | null => {
    if (selection?.kind === 'zone') {
      const z = twin.zones.find((zz) => zz.id === selection.id)
      return z ? [z.center[0], 0, z.center[1]] : null
    }
    if (selection?.kind === 'sensor') {
      const s = sensors.find((ss) => ss.id === selection.id)
      return s ? [s.position[0], 0, s.position[2]] : null
    }
    if (selection?.kind === 'infra') {
      const i = twin.infrastructure.find((ii) => ii.id === selection.id)
      if (i && 'position' in i) return [i.position[0], 0, i.position[2]]
    }
    return null
  }, [selection, twin, sensors])

  return (
    <>
      <color attach="background" args={[night ? '#060b09' : '#9fb8c4']} />
      <fog attach="fog" args={[night ? '#060b09' : '#a9bcc2', dist * 1.6, dist * 6]} />
      {!night && <Sky sunPosition={sunDir.map((v) => v * 1000) as [number, number, number]} turbidity={4 + cloud * 8} rayleigh={1.2 + cloud} mieCoefficient={0.006} distance={dist * 10} />}
      {night && <Stars radius={dist * 4} depth={dist} count={2500} factor={6} fade speed={reducedMotion ? 0 : 0.4} />}

      <hemisphereLight args={[night ? '#1b2a3a' : '#dfeaf0', '#3a2e22', night ? 0.25 : 0.55 + 0.35 * daylight]} />
      <directionalLight
        castShadow={!night}
        position={[center[0] + sunDir[0] * dist, Math.max(sunDir[1], 0.05) * dist, center[1] + sunDir[2] * dist]}
        intensity={night ? 0.15 : (1.6 - cloud * 0.9) * daylight}
        color={night ? '#9db4d6' : '#fff1d6'}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-dist}
        shadow-camera-right={dist}
        shadow-camera-top={dist}
        shadow-camera-bottom={-dist}
        shadow-camera-far={dist * 4}
        shadow-bias={-0.0004}
      />

      <Terrain center={center} size={dist * 5} />

      {twin.zones.map((z, idx) => (
        <ZoneMesh
          key={z.id}
          zone={z}
          index={idx}
          selected={selectedZone === z.id}
          heatmap={layers.moisture}
          showCanopy={layers.crops}
          showLabel={layers.labels}
          onSelect={() => onSelect({ kind: 'zone', id: z.id })}
        />
      ))}
      {layers.crops &&
        twin.zones.map((z) => <CropField key={z.id} zone={z} wind={wind} animate={!reducedMotion} onSelect={() => onSelect({ kind: 'zone', id: z.id })} />)}

      {layers.sensors &&
        sensors.map((s) => (
          <SensorNode key={s.id} sensor={s} now={now} selected={selectedSensor === s.id} showLabel={layers.labels} animate={!reducedMotion} onSelect={() => onSelect({ kind: 'sensor', id: s.id })} />
        ))}

      {twin.infrastructure.map((item) => {
        const layerOn =
          item.kind === 'pipe' || item.kind === 'pump' || item.kind === 'tank' || item.kind === 'channel'
            ? layers.irrigation
            : item.kind === 'solar'
              ? layers.solar
              : layers.infrastructure
        if (!layerOn) return null
        return (
          <InfraItem
            key={item.id}
            item={item}
            selected={selectedInfra === item.id}
            wind={wind}
            animate={!reducedMotion}
            showLabel={layers.labels}
            onSelect={() => onSelect({ kind: 'infra', id: item.id })}
          />
        )
      })}

      {layers.landscape && <Windbreak twin={twin} wind={wind} animate={!reducedMotion} />}
      {raining && !reducedMotion && <Rain center={center} size={dist * 1.4} />}

      <Controls center={center} dist={dist} focus={focus} resetSignal={resetSignal} reducedMotion={reducedMotion} />
    </>
  )
}

// --- camera ------------------------------------------------------------------
function Controls({ center, dist, focus, resetSignal, reducedMotion }: { center: XZ; dist: number; focus: [number, number, number] | null; resetSignal: number; reducedMotion: boolean }) {
  const ref = useRef<ComponentRef<typeof OrbitControls>>(null)
  const camera = useThree((s) => s.camera)
  const invalidate = useThree((s) => s.invalidate)
  const target = useRef(new THREE.Vector3(center[0], 0, center[1]))

  useEffect(() => {
    if (focus) target.current.set(...focus)
  }, [focus])
  useEffect(() => {
    target.current.set(center[0], 0, center[1])
    camera.position.set(center[0] + dist * 0.55, dist * 0.55, center[1] + dist * 0.75)
    invalidate()
  }, [resetSignal, center, dist, camera, invalidate])

  useFrame(() => {
    const c = ref.current
    if (!c) return
    if (reducedMotion) c.target.copy(target.current)
    else c.target.lerp(target.current, 0.08)
    c.update()
  })
  return (
    <OrbitControls
      ref={ref}
      makeDefault
      enableDamping={!reducedMotion}
      dampingFactor={0.08}
      maxPolarAngle={Math.PI / 2 - 0.06}
      minDistance={8}
      maxDistance={dist * 3}
      screenSpacePanning={false}
    />
  )
}

// --- ground ------------------------------------------------------------------
function Terrain({ center, size }: { center: XZ; size: number }) {
  const geometry = useMemo(() => {
    const g = new THREE.PlaneGeometry(size, size, 96, 96)
    g.rotateX(-Math.PI / 2)
    const pos = g.attributes.position as THREE.BufferAttribute
    const flat = size * 0.18 // keep the farm itself flat; gentle undulation beyond it
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const z = pos.getZ(i)
      const r = Math.hypot(x, z)
      const t = THREE.MathUtils.smoothstep(r, flat, flat * 2.2)
      const h = (Math.sin(x * 0.012) * Math.cos(z * 0.015) * 6 + Math.sin((x + z) * 0.03) * 1.5) * t
      pos.setY(i, h - 0.05)
    }
    g.computeVertexNormals()
    return g
  }, [size])
  useEffect(() => () => geometry.dispose(), [geometry])
  return (
    <mesh geometry={geometry} position={[center[0], 0, center[1]]} receiveShadow>
      <meshStandardMaterial color={GRASS} roughness={0.95} />
    </mesh>
  )
}

function shapeFromPolygon(polygon: readonly XZ[]): THREE.Shape {
  // Shape lives in XY; after rotateX(-90°) shape (x, y) maps to world (x, -y), so use y = -z.
  const shape = new THREE.Shape()
  polygon.forEach(([x, z], i) => (i === 0 ? shape.moveTo(x, -z) : shape.lineTo(x, -z)))
  shape.closePath()
  return shape
}

function ZoneMesh({ zone, index, selected, heatmap, showCanopy, showLabel, onSelect }: { zone: TwinZone; index: number; selected: boolean; heatmap: boolean; showCanopy: boolean; showLabel: boolean; onSelect: () => void }) {
  const geometry = useMemo(() => {
    const g = new THREE.ExtrudeGeometry(shapeFromPolygon(zone.polygon as XZ[]), { depth: 0.25, bevelEnabled: false })
    g.rotateX(-Math.PI / 2)
    return g
  }, [zone.polygon])
  const outline = useMemo(() => new THREE.EdgesGeometry(geometry, 30), [geometry])
  useEffect(() => () => (geometry.dispose(), outline.dispose()), [geometry, outline])
  const soil = index % 2 ? SOIL_DRY : SOIL
  // From a distance a field reads as canopy cover over soil; cover comes from the crop's growth stage.
  const color = heatmap ? moistureColor(zone.soil_moisture) : showCanopy ? canopyTint(soil, canopySize(zone).cover) : soil
  const health = healthStyle(zone)
  return (
    <group>
      <mesh
        geometry={geometry}
        receiveShadow
        onClick={(e: ThreeEvent<MouseEvent>) => (e.stopPropagation(), onSelect())}
        onPointerOver={(e) => (e.stopPropagation(), (document.body.style.cursor = 'pointer'))}
        onPointerOut={() => (document.body.style.cursor = '')}
      >
        <meshStandardMaterial color={color} roughness={0.9} emissive={selected ? SELECT : '#000'} emissiveIntensity={selected ? 0.12 : 0} />
      </mesh>
      <lineSegments geometry={outline} position={[0, 0.02, 0]}>
        <lineBasicMaterial color={selected ? SELECT : (health.outline ?? '#2b2219')} transparent opacity={selected || health.outline ? 1 : 0.5} />
      </lineSegments>
      {zone.irrigating && <IrrigationMist zone={zone} />}
      {showLabel && <Label text={`${zone.name}${zone.irrigating ? ' · irrigating' : ''}${health.label}`} position={[zone.center[0], 4, zone.center[1]]} />}
    </group>
  )
}

// --- crops (instanced, GPU wind sway) ------------------------------------------
function useSwayMaterial(color: string, wind: number, animate: boolean) {
  const uniforms = useRef({ uTime: { value: 0 }, uWind: { value: 0 } })
  const material = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.85 })
    m.onBeforeCompile = (shader) => {
      shader.uniforms.uTime = uniforms.current.uTime
      shader.uniforms.uWind = uniforms.current.uWind
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nuniform float uTime;\nuniform float uWind;')
        .replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
           #ifdef USE_INSTANCING
             vec3 ip = vec3(instanceMatrix[3][0], 0.0, instanceMatrix[3][2]);
             float phase = ip.x * 0.21 + ip.z * 0.17;
             float bend = max(position.y, 0.0);
             transformed.x += sin(uTime * 1.7 + phase) * uWind * 0.06 * bend;
             transformed.z += cos(uTime * 1.3 + phase) * uWind * 0.03 * bend;
           #endif`,
        )
    }
    return m
  }, [color])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => {
    uniforms.current.uWind.value = animate ? Math.min(wind, 12) : 0
  }, [wind, animate])
  useFrame((_, dt) => {
    if (animate) uniforms.current.uTime.value += dt
  })
  return material
}

const GEOMETRIES = {
  grass: () => new THREE.ConeGeometry(0.18, 1.1, 4).translate(0, 0.55, 0),
  bush: () => new THREE.IcosahedronGeometry(0.42, 0).translate(0, 0.38, 0),
  trunk: () => new THREE.CylinderGeometry(0.15, 0.22, 1.6, 6).translate(0, 0.8, 0),
  canopy: () => new THREE.IcosahedronGeometry(1.6, 0).translate(0, 2.6, 0),
}

function CropField({ zone, wind, animate, onSelect }: { zone: TwinZone; wind: number; animate: boolean; onSelect: () => void }) {
  const form = zone.crop?.form
  // Orchards: individual trees (5 m spacing is visible). Row crops: row stripes.
  const plants = useMemo(() => (form === 'tree' ? cropInstances(zone) : []), [zone, form])
  const rows = useMemo(() => cropRows(zone), [zone])
  const canopy = canopySize(zone)
  const leafColor = healthStyle(zone).leaf ?? (zone.crop?.status === 'planned' ? '#7d8a52' : form === 'grass' ? '#8f9f45' : '#4c8a3a')
  const leaf = useSwayMaterial(leafColor, wind, animate)
  const trunk = useMemo(() => new THREE.MeshStandardMaterial({ color: '#5b4129', roughness: 1 }), [])
  useEffect(() => () => trunk.dispose(), [trunk])
  if (!form) return null
  const handle = (e: ThreeEvent<MouseEvent>) => (e.stopPropagation(), onSelect())
  if (form === 'tree') {
    if (!plants.length) return null
    return (
      <group onClick={handle}>
        <Instances geometryKey="trunk" material={trunk} plants={plants} />
        <Instances geometryKey="canopy" material={leaf} plants={plants} />
      </group>
    )
  }
  if (!rows.length || canopy.width <= 0) return null
  return (
    <group onClick={handle}>
      <RowStripes rows={rows} width={canopy.width} height={canopy.height} material={leaf} />
    </group>
  )
}

function RowStripes({ rows, width, height, material }: { rows: RowSegment[]; width: number; height: number; material: THREE.Material }) {
  const ref = useRef<THREE.InstancedMesh>(null)
  // Unit box with its base on the ground, so the sway shader bends the top, not the base.
  const geometry = useMemo(() => new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0), [])
  useEffect(() => () => geometry.dispose(), [geometry])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    rows.forEach((r, i) => {
      m.compose(new THREE.Vector3(r.x, 0.25, r.z), q, new THREE.Vector3(r.alongX ? r.length : width, height, r.alongX ? width : r.length))
      mesh.setMatrixAt(i, m)
    })
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
  }, [rows, width, height])
  return <instancedMesh ref={ref} args={[geometry, material, rows.length]} castShadow receiveShadow />
}

function Instances({ geometryKey, material, plants }: { geometryKey: keyof typeof GEOMETRIES; material: THREE.Material; plants: ReturnType<typeof cropInstances> }) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const geometry = useMemo(() => GEOMETRIES[geometryKey](), [geometryKey])
  useEffect(() => () => geometry.dispose(), [geometry])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const up = new THREE.Vector3(0, 1, 0)
    plants.forEach((p, i) => {
      q.setFromAxisAngle(up, p.rotation)
      m.compose(new THREE.Vector3(p.x, 0.25, p.z), q, new THREE.Vector3(p.scale, p.scale, p.scale))
      mesh.setMatrixAt(i, m)
    })
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
  }, [plants])
  return <instancedMesh ref={ref} args={[geometry, material, plants.length]} castShadow receiveShadow />
}

function IrrigationMist({ zone }: { zone: TwinZone }) {
  const { minX, maxX, minZ, maxZ } = bbox(zone.polygon as XZ[])
  return (
    <mesh position={[(minX + maxX) / 2, 0.6, (minZ + maxZ) / 2]} rotation-x={-Math.PI / 2}>
      <planeGeometry args={[maxX - minX, maxZ - minZ]} />
      <meshBasicMaterial color={WATER} transparent opacity={0.18} depthWrite={false} />
    </mesh>
  )
}

// --- sensors -------------------------------------------------------------------
function SensorNode({ sensor, now, selected, showLabel, animate, onSelect }: { sensor: TwinSensor; now: number; selected: boolean; showLabel: boolean; animate: boolean; onSelect: () => void }) {
  const status = sensorStatus(sensor.latest, now)
  const ring = useRef<THREE.Mesh>(null)
  const lastSeen = useRef<string | null>(null)
  const pulse = useRef(0)
  useEffect(() => {
    const ts = sensor.latest?.recorded_at ?? null
    if (lastSeen.current && ts && ts !== lastSeen.current) pulse.current = 1 // a new reading just arrived
    lastSeen.current = ts
  }, [sensor.latest?.recorded_at])
  useFrame((_, dt) => {
    const r = ring.current
    if (!r) return
    if (!animate) {
      r.visible = false
      return
    }
    pulse.current = Math.max(0, pulse.current - dt * 0.8)
    r.visible = pulse.current > 0
    const s = 1 + (1 - pulse.current) * 3
    r.scale.set(s, s, s)
    ;(r.material as THREE.MeshBasicMaterial).opacity = pulse.current * 0.6
  })
  const [x, , z] = sensor.position
  const h = 4 // marker scale (a UI marker, not the device's physical size)
  return (
    <group position={[x, 0.25, z]}>
      <mesh position={[0, h / 2, 0]} castShadow>
        <cylinderGeometry args={[0.12, 0.16, h, 6]} />
        <meshStandardMaterial color="#c9c4b5" metalness={0.4} roughness={0.5} />
      </mesh>
      <mesh
        position={[0, h + 0.6, 0]}
        onClick={(e: ThreeEvent<MouseEvent>) => (e.stopPropagation(), onSelect())}
        onPointerOver={(e) => (e.stopPropagation(), (document.body.style.cursor = 'pointer'))}
        onPointerOut={() => (document.body.style.cursor = '')}
      >
        <sphereGeometry args={[selected ? 1.3 : 0.9, 16, 12]} />
        <meshStandardMaterial color={status.color} emissive={status.color} emissiveIntensity={selected ? 0.9 : 0.35} />
      </mesh>
      <mesh ref={ring} position={[0, 0.05, 0]} rotation-x={-Math.PI / 2} visible={false}>
        <ringGeometry args={[1.2, 1.5, 32]} />
        <meshBasicMaterial color={status.color} transparent opacity={0} depthWrite={false} />
      </mesh>
      {(selected || (showLabel && sensor.sensor_type === 'soil_moisture')) && sensor.latest && (
        <Label
          text={`${sensor.latest.value.toFixed(1)} ${sensor.unit}${sensor.is_simulated ? ' · sim' : ''}`}
          position={[0, h + 2.6, 0]}
          size={0.026}
          mono
        />
      )}
    </group>
  )
}

// --- labels ---------------------------------------------------------------------
/**
 * Text label as a camera-facing sprite with a canvas texture, at a constant on-screen size.
 * (drei's <Html> creates a separate React root per label; sprites are cheaper and avoid that.)
 */
function Label({
  text,
  position,
  size = 0.032,
  color = '#f4f1e8',
  mono = false,
}: {
  text: string
  position: [number, number, number]
  size?: number
  color?: string
  mono?: boolean
}) {
  const { texture, aspect } = useMemo(() => {
    const scale = 2 // draw at 2x for crisp text on high-DPI screens
    const fontPx = 26 * scale
    const font = `${mono ? '500' : '600'} ${fontPx}px ${mono ? '"JetBrains Mono Variable", ui-monospace' : '"Inter Variable", system-ui'}, sans-serif`
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) return { texture: null, aspect: 1 }
    ctx.font = font
    const padX = 14 * scale
    const w = Math.ceil(ctx.measureText(text).width + padX * 2)
    const h = Math.ceil(fontPx * 1.55)
    canvas.width = w
    canvas.height = h
    ctx.font = font
    ctx.fillStyle = 'rgba(8, 16, 12, 0.78)'
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.14)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.roundRect(1, 1, w - 2, h - 2, h / 2)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = color
    ctx.textBaseline = 'middle'
    ctx.fillText(text, padX, h / 2 + 1)
    const tex = new THREE.CanvasTexture(canvas)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = 4
    return { texture: tex, aspect: w / h }
  }, [text, color, mono])
  useEffect(() => () => texture?.dispose(), [texture])
  if (!texture) return null
  return (
    <sprite position={position} scale={[size * aspect, size, 1]} renderOrder={10}>
      <spriteMaterial map={texture} transparent depthTest={false} sizeAttenuation={false} />
    </sprite>
  )
}

// --- infrastructure ---------------------------------------------------------------
function Selectable({ children, selected, onSelect, position }: { children: ReactNode; selected: boolean; onSelect: () => void; position?: [number, number, number] }) {
  return (
    <group
      position={position}
      onClick={(e: ThreeEvent<MouseEvent>) => (e.stopPropagation(), onSelect())}
      onPointerOver={(e) => (e.stopPropagation(), (document.body.style.cursor = 'pointer'))}
      onPointerOut={() => (document.body.style.cursor = '')}
      scale={selected ? 1.06 : 1}
    >
      {children}
    </group>
  )
}

function InfraItem({ item, selected, wind, animate, showLabel, onSelect }: { item: Infra; selected: boolean; wind: number; animate: boolean; showLabel: boolean; onSelect: () => void }) {
  switch (item.kind) {
    case 'farmhouse':
      return (
        <Selectable selected={selected} onSelect={onSelect} position={item.position}>
          <mesh position={[0, 3, 0]} castShadow receiveShadow>
            <boxGeometry args={[14, 6, 10]} />
            <meshStandardMaterial color="#d8cdb6" roughness={0.9} />
          </mesh>
          <mesh position={[0, 7.4, 0]} rotation-y={Math.PI / 4} castShadow>
            <coneGeometry args={[10.5, 3.2, 4]} />
            <meshStandardMaterial color="#8c4f36" roughness={0.8} />
          </mesh>
        </Selectable>
      )
    case 'shed':
      return (
        <Selectable selected={selected} onSelect={onSelect} position={item.position}>
          <mesh position={[0, 2.5, 0]} castShadow receiveShadow>
            <boxGeometry args={[16, 5, 9]} />
            <meshStandardMaterial color="#9a9c8f" metalness={0.3} roughness={0.6} />
          </mesh>
        </Selectable>
      )
    case 'road':
    case 'channel':
      return <Strip item={item} />
    case 'tank':
      return <Tank item={item} selected={selected} onSelect={onSelect} showLabel={showLabel} />
    case 'pump':
      return <Pump item={item} selected={selected} onSelect={onSelect} animate={animate} />
    case 'pipe':
      return <Pipe item={item} animate={animate} />
    case 'weather_station':
      return <WeatherStation item={item} selected={selected} onSelect={onSelect} wind={wind} animate={animate} />
    case 'gateway':
      return <Gateway item={item} selected={selected} onSelect={onSelect} animate={animate} />
    case 'solar':
      return <Solar item={item} selected={selected} onSelect={onSelect} />
  }
}

function Strip({ item }: { item: InfraOf<'road'> | InfraOf<'channel'> }) {
  const [x0, z0] = item.from
  const [x1, z1] = item.to
  const len = Math.hypot(x1 - x0, z1 - z0)
  const angle = Math.atan2(z1 - z0, x1 - x0)
  const water = item.kind === 'channel'
  return (
    <mesh position={[(x0 + x1) / 2, water ? 0.02 : 0.06, (z0 + z1) / 2]} rotation={[-Math.PI / 2, 0, -angle]} receiveShadow>
      <planeGeometry args={[len, item.width]} />
      <meshStandardMaterial color={water ? WATER : ROAD} roughness={water ? 0.15 : 1} metalness={water ? 0.2 : 0} />
    </mesh>
  )
}

function Tank({ item, selected, onSelect, showLabel }: { item: InfraOf<'tank'>; selected: boolean; onSelect: () => void; showLabel: boolean }) {
  const level = item.level_pct
  const H = 6
  const fill = level == null ? 0 : (Math.min(100, Math.max(0, level)) / 100) * H
  return (
    <Selectable selected={selected} onSelect={onSelect} position={item.position}>
      <mesh position={[0, H / 2 + 0.6, 0]} castShadow>
        <cylinderGeometry args={[3, 3, H, 28, 1, true]} />
        <meshStandardMaterial color="#c8d2d4" transparent opacity={0.35} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {fill > 0 && (
        <mesh position={[0, fill / 2 + 0.6, 0]}>
          <cylinderGeometry args={[2.9, 2.9, fill, 28]} />
          <meshStandardMaterial color={WATER} roughness={0.2} />
        </mesh>
      )}
      <mesh position={[0, 0.3, 0]} receiveShadow>
        <cylinderGeometry args={[3.4, 3.4, 0.6, 28]} />
        <meshStandardMaterial color="#8a8578" />
      </mesh>
      {showLabel && <Label text={`Tank ${level == null ? 'no sensor' : `${level.toFixed(0)}%`}`} position={[0, H + 2.5, 0]} size={0.026} color="#cfe3ea" />}
    </Selectable>
  )
}

function Pump({ item, selected, onSelect, animate }: { item: InfraOf<'pump'>; selected: boolean; onSelect: () => void; animate: boolean }) {
  const wheel = useRef<THREE.Mesh>(null)
  useFrame((_, dt) => {
    if (wheel.current && animate && item.running) wheel.current.rotation.z += dt * 6
  })
  return (
    <Selectable selected={selected} onSelect={onSelect} position={item.position}>
      <mesh position={[0, 0.8, 0]} castShadow>
        <boxGeometry args={[2.2, 1.6, 1.6]} />
        <meshStandardMaterial color={item.running ? '#3a7a5c' : '#5f6b63'} metalness={0.4} roughness={0.5} />
      </mesh>
      <mesh ref={wheel} position={[0, 0.9, 0.9]}>
        <torusGeometry args={[0.55, 0.1, 6, 12]} />
        <meshStandardMaterial color="#c9c4b5" />
      </mesh>
    </Selectable>
  )
}

function Pipe({ item, animate }: { item: InfraOf<'pipe'>; animate: boolean }) {
  const curve = useMemo(() => {
    const path = new THREE.CurvePath<THREE.Vector3>()
    for (let i = 0; i < item.path.length - 1; i++) {
      const [ax, az] = item.path[i]!
      const [bx, bz] = item.path[i + 1]!
      path.add(new THREE.LineCurve3(new THREE.Vector3(ax, 0.35, az), new THREE.Vector3(bx, 0.35, bz)))
    }
    return path
  }, [item.path])
  const tube = useMemo(() => new THREE.TubeGeometry(curve as unknown as THREE.Curve<THREE.Vector3>, Math.max(16, item.path.length * 24), 0.22, 6, false), [curve, item.path.length])
  useEffect(() => () => tube.dispose(), [tube])
  const drops = useRef<THREE.InstancedMesh>(null)
  const N = 24
  const offset = useRef(0)
  useFrame((_, dt) => {
    const mesh = drops.current
    if (!mesh) return
    mesh.visible = item.flowing && animate
    if (!mesh.visible) return
    offset.current = (offset.current + dt * 0.06) % 1
    const m = new THREE.Matrix4()
    for (let i = 0; i < N; i++) {
      const t = (offset.current + i / N) % 1
      const p = curve.getPointAt(t)
      m.makeTranslation(p.x, p.y + 0.05, p.z)
      mesh.setMatrixAt(i, m)
    }
    mesh.instanceMatrix.needsUpdate = true
  })
  return (
    <group>
      <mesh geometry={tube} castShadow>
        <meshStandardMaterial color={item.flowing ? '#3f86a6' : '#6b7366'} roughness={0.5} metalness={0.2} />
      </mesh>
      <instancedMesh ref={drops} args={[undefined, undefined, N]} visible={false}>
        <sphereGeometry args={[0.28, 8, 6]} />
        <meshBasicMaterial color="#bfe3f2" />
      </instancedMesh>
    </group>
  )
}

function WeatherStation({ item, selected, onSelect, wind, animate }: { item: InfraOf<'weather_station'>; selected: boolean; onSelect: () => void; wind: number; animate: boolean }) {
  const cups = useRef<THREE.Group>(null)
  useFrame((_, dt) => {
    if (cups.current && animate) cups.current.rotation.y += dt * Math.min(wind, 15) * 1.2
  })
  return (
    <Selectable selected={selected} onSelect={onSelect} position={item.position}>
      <mesh position={[0, 3, 0]} castShadow>
        <cylinderGeometry args={[0.08, 0.1, 6, 6]} />
        <meshStandardMaterial color="#d9d6cc" metalness={0.5} />
      </mesh>
      <mesh position={[0, 4.2, 0]} castShadow>
        <boxGeometry args={[0.8, 0.8, 0.8]} />
        <meshStandardMaterial color="#f2efe6" />
      </mesh>
      <group ref={cups} position={[0, 6.1, 0]}>
        {[0, 1, 2].map((i) => (
          <mesh key={i} position={[Math.cos((i * 2 * Math.PI) / 3) * 0.6, 0, Math.sin((i * 2 * Math.PI) / 3) * 0.6]}>
            <sphereGeometry args={[0.16, 8, 6]} />
            <meshStandardMaterial color="#c9c4b5" />
          </mesh>
        ))}
      </group>
    </Selectable>
  )
}

function Gateway({ item, selected, onSelect, animate }: { item: InfraOf<'gateway'>; selected: boolean; onSelect: () => void; animate: boolean }) {
  const ring = useRef<THREE.Mesh>(null)
  const t = useRef(0)
  useFrame((_, dt) => {
    const r = ring.current
    if (!r) return
    if (!animate) return void (r.visible = false)
    t.current = (t.current + dt * 0.5) % 1
    r.visible = true
    const s = 1 + t.current * 6
    r.scale.set(s, s, s)
    ;(r.material as THREE.MeshBasicMaterial).opacity = (1 - t.current) * 0.35
  })
  return (
    <Selectable selected={selected} onSelect={onSelect} position={item.position}>
      <mesh position={[0, 2.2, 0]} castShadow>
        <cylinderGeometry args={[0.07, 0.09, 4.4, 6]} />
        <meshStandardMaterial color="#d9d6cc" metalness={0.5} />
      </mesh>
      <mesh position={[0, 4.6, 0]}>
        <boxGeometry args={[0.5, 0.7, 0.3]} />
        <meshStandardMaterial color="#2b3a33" emissive="#8fbf7a" emissiveIntensity={0.4} />
      </mesh>
      <mesh ref={ring} position={[0, 4.6, 0]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.6, 0.7, 32]} />
        <meshBasicMaterial color="#8fbf7a" transparent opacity={0} depthWrite={false} />
      </mesh>
    </Selectable>
  )
}

function Solar({ item, selected, onSelect }: { item: InfraOf<'solar'>; selected: boolean; onSelect: () => void }) {
  return (
    <Selectable selected={selected} onSelect={onSelect} position={item.position}>
      {[-1, 0, 1].map((row) =>
        [-2, -1, 0, 1, 2].map((col) => (
          <mesh key={`${row}${col}`} position={[col * 3.4, 1.4, row * 4]} rotation-x={-0.45} castShadow>
            <boxGeometry args={[3.2, 0.08, 2]} />
            <meshStandardMaterial color="#1e2f4a" metalness={0.6} roughness={0.25} />
          </mesh>
        )),
      )}
    </Selectable>
  )
}

// --- landscape -------------------------------------------------------------------
function Windbreak({ twin, wind, animate }: { twin: FarmTwin; wind: number; animate: boolean }) {
  const plants = useMemo(() => {
    const [x0, z0] = twin.extent.min
    const [x1, z1] = twin.extent.max
    const pad = 30
    const out: ReturnType<typeof cropInstances> = []
    const edge = (ax: number, az: number, bx: number, bz: number) => {
      const len = Math.hypot(bx - ax, bz - az)
      for (let d = 0; d <= len; d += 9) {
        const t = d / len
        const r = hash01(ax + d, az, 7)
        out.push({ x: ax + (bx - ax) * t + (r - 0.5) * 4, z: az + (bz - az) * t + (hash01(d, bz, 3) - 0.5) * 4, scale: 0.9 + r * 0.6, rotation: r * 6 })
      }
    }
    edge(x0 - pad, z0 - pad, x1 + pad, z0 - pad) // north boundary
    edge(x1 + pad, z0 - pad, x1 + pad, z1 + pad) // east boundary
    return out
  }, [twin.extent])
  const leaf = useSwayMaterial('#355f2e', wind * 0.4, animate)
  const trunk = useMemo(() => new THREE.MeshStandardMaterial({ color: '#4e3a26', roughness: 1 }), [])
  useEffect(() => () => trunk.dispose(), [trunk])
  return (
    <group>
      <Instances geometryKey="trunk" material={trunk} plants={plants} />
      <Instances geometryKey="canopy" material={leaf} plants={plants} />
    </group>
  )
}

function Rain({ center, size }: { center: XZ; size: number }) {
  const ref = useRef<THREE.Points>(null)
  const geometry = useMemo(() => {
    const n = 4000
    const arr = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      arr[i * 3] = center[0] + (hash01(i, 1) - 0.5) * size
      arr[i * 3 + 1] = hash01(i, 2) * 60
      arr[i * 3 + 2] = center[1] + (hash01(i, 3) - 0.5) * size
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3))
    return g
  }, [center, size])
  useEffect(() => () => geometry.dispose(), [geometry])
  useFrame((_, dt) => {
    const points = ref.current
    if (!points) return
    const pos = points.geometry.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < pos.count; i++) {
      let y = pos.getY(i) - dt * 30
      if (y < 0) y += 60
      pos.setY(i, y)
    }
    pos.needsUpdate = true
  })
  return (
    <points ref={ref} geometry={geometry}>
      <pointsMaterial color="#bcd3de" size={0.25} transparent opacity={0.6} depthWrite={false} />
    </points>
  )
}
