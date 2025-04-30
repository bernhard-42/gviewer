import * as THREE from "three";
import { TrackballControls } from "three/addons/controls/TrackballControls.js";

const scale = 10;
const gridSize = 10 * scale;
const instanceCount = gridSize * gridSize;

// Scene setup
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(
    75,
    window.innerWidth / window.innerHeight,
    0.1,
    10000
);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);
camera.position.z = 20 * scale;

// Meshes

// const vertices = new Float32Array([-0.5, -0.5, 0.5, -0.5, 0.5, 0.5, -0.5, 0.5]);
// const dist = 3;
const vertices = new Float32Array([
    0, 0, 3, 0, 3, 1, 1, 1, 1, 2, 3, 2, 3, 3, 1, 3, 1, 5, 0, 5
]);
const dist = 8;
const n = vertices.length / 2;
const points = new Array(n);
for (let i = 0; i < n; i++) {
    points[i] = new THREE.Vector2(vertices[2 * i], vertices[2 * i + 1]);
}

const shape = new THREE.Shape(points);

const extrudeSettings = {
    depth: 1,
    bevelEnabled: false
};
const cubeGeometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);

const cubeMaterial = new THREE.MeshBasicMaterial({
    color: 0xff0000,
    polygonOffset: true,
    polygonOffsetFactor: 1.0,
    polygonOffsetUnits: 1.0
});

const cubeMesh = new THREE.InstancedMesh(
    cubeGeometry,
    cubeMaterial,
    instanceCount
);

// Edges

var edges = new THREE.EdgesGeometry(cubeGeometry);
var edgeGeom = new THREE.InstancedBufferGeometry().copy(edges);
var edgeOffset = [];

var instMat = new THREE.LineBasicMaterial({
    color: 0xffffff,
    onBeforeCompile: (shader) => {
        shader.vertexShader = `
    	attribute vec3 offset;
      ${shader.vertexShader}
    `.replace(
            `#include <begin_vertex>`,
            `
      #include <begin_vertex>
      transformed += offset;
      `
        );
    }
});

// (Reuse the same offsets for cube positions)
const dummy = new THREE.Object3D();
for (let i = -gridSize / 2; i < gridSize / 2; i++) {
    for (let j = -gridSize / 2; j < gridSize / 2; j++) {
        dummy.position.set(i * dist, j * dist, 0);
        dummy.updateMatrix();
        cubeMesh.setMatrixAt(
            (i + gridSize / 2) * gridSize + (j + gridSize / 2),
            dummy.matrix
        );
        edgeOffset.push(j * dist, i * dist, 0);
    }
}
cubeMesh.instanceMatrix.needsUpdate = true;
scene.add(cubeMesh);

edgeGeom.setAttribute(
    "offset",
    new THREE.InstancedBufferAttribute(new Float32Array(edgeOffset), 3)
);
edgeGeom.instanceCount = Infinity;
var instLines = new THREE.LineSegments(edgeGeom, instMat);
scene.add(instLines);

const controls = new TrackballControls(camera, renderer.domElement);

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();
