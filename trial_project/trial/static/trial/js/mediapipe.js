import {
  FaceLandmarker,
  FilesetResolver
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

let faceLandmarker = null;

export async function initMediaPipe() {

    const vision = await FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
    );

    faceLandmarker = await FaceLandmarker.createFromOptions(
        vision,
        {
            baseOptions:{
                modelAssetPath:
                "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            },
            runningMode:"VIDEO",
            numFaces:1,
            outputFaceBlendshapes:true,
            outputFacialTransformationMatrixes:true
        }
    );

    console.log("MediaPipe Ready");
}

export function getFaceLandmarker(){
    return faceLandmarker;
}