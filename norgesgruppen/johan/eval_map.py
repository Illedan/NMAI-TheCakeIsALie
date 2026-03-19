import contextlib, io, numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

def score(prediction_filename, truth_filename):
    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO(truth_filename)
        coco_dt = coco_gt.loadRes(prediction_filename)
        mAPs = []
        for useCategories in range(2):
            coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
            coco_eval.params.useCats = useCategories
            coco_eval.params.iouThrs = [0.5]
            coco_eval.evaluate()
            coco_eval.accumulate()
            precision = coco_eval.eval["precision"][0, :, 0, 0, 2]
            mAP = np.mean(precision[precision > -1])
            mAPs.append(mAP)
        return mAPs[0]*0.7 + mAPs[1]*0.3

print(f"{score('out.json', 'annotations.json'):.3f}")
