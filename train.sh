# Finetune p5 models with multiple GPUs

data=stomavision
batch_size=8

# python seg/segment/train.py \
#     --workers 6 \
#     --device cpu \
#     --batch-size $batch_size \
#     --cfg cfg/training/yolov7-seg.yaml \
#     --data data/$data.yaml \
#     --img 640 \
#     --weights 'model/yolov7-seg.pt' \
#     --name yolov7-abrc-$data \
#     --hyp hyp/hyp.scratch.abrc.yaml

# sample command for distributed training with 2 gpu
python -m torch.distributed.run \
    --nproc_per_node 2 \
    --master_port 9527 \
    seg/segment/train.py \
    --workers 32 \
    --device 0,1 \
    --batch-size $batch_size \
    --cfg cfg/training/yolov7-seg.yaml \
    --data data/$data.yaml \
    --img 640 \
    --weights 'model/yolov7-seg.pt' \
    --name $data-$batch_size \
    --hyp hyp/hyp.scratch.abrc.yaml \
    --epochs 500

# Finetune p5 models with single GPU
#python seg/segment/train.py \
#--workers 8 \
#--device 2 \
#--batch-size 16 \
#--data data/stomata200-mix.yaml \
#--img 640 \
#--cfg cfg/training/yolov7-seg.yaml \
#--weights 'model/yolov7-seg.pt' \
#--name yolov7-abrc-stomata200-mix \
#--hyp hyp/hyp.scratch.abrc.yaml
